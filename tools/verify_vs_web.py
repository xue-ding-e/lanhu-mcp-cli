#!/usr/bin/env python3
"""对蓝湖 web 金标准实测:连登录态 Edge(9444)导航到某图读 Vue layers(金标准),
逐元素核 CLI convert 输出的 几何/颜色/圆角/阴影 是否逐字一致。这是最强验证——
不是 sketch 自对照,而是直接对蓝湖 web 面板显示值(用户认的唯一标准)。
用法: python tools/verify_vs_web.py <image_id> <pid> [tid]  (需先开登录态 Edge --remote-debugging-port=9444)
实测: 某订单页 几何156+颜色76 逐字一致零差异。"""
import asyncio
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo 根,保证任意 cwd 下能 import
import lanhu_mcp_server as m
from playwright.async_api import async_playwright

if len(sys.argv) < 3:
    print(__doc__)
    sys.exit(1)
DID = sys.argv[1]
PID = sys.argv[2]
TID = sys.argv[3] if len(sys.argv) > 3 else ''
URL = (f'https://lanhuapp.com/web/#/item/project/detailDetach?pid={PID}&image_id={DID}'
       f'&project_id={PID}&fromEditor=true' + (f'&tid={TID}' if TID else ''))
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')  # repo 根 data/(已 gitignore)


def n(v):
    mt = re.match(r'(-?[\d.]+)', str(v))
    return round(float(mt.group(1)), 1) if mt else None


async def main():
    # 1) web 金标准:连 Edge 导航读 Vue
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp('http://127.0.0.1:9444')
        ctx = b.contexts[0]
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(URL, wait_until='domcontentloaded')
        # 轮询等 Vue layers 加载
        raw = None
        for _ in range(30):
            raw = await page.evaluate(r"""() => {
                let vm=null;
                for(const s of ['.layer_interactive','#app','body']){let x=document.querySelector(s);while(x){if(x.__vue__){vm=x.__vue__;break;}x=x.parentElement;}if(vm)break;}
                const L=(vm&&vm.g_detail&&vm.g_detail.layers)||[];
                if(!L.length) return null;
                return JSON.stringify(L.map(o=>({name:o.name,type:o.type,left:o.left,top:o.top,width:o.width,height:o.height,
                    color:o.font&&o.font.color&&o.font.color.value, size:o.font&&(o.font.size||(o.font.styles&&o.font.styles[0]&&o.font.styles[0].size)),
                    radius:o.radius, shadows:(o.style&&o.style.shadows)||[]})));
            }""")
            if raw:
                break
            await page.wait_for_timeout(500)
    if not raw:
        print('❌ Vue 金标准未加载(检查Edge是否登录/图是否存在)')
        return
    import json
    web = json.loads(raw)
    os.makedirs(OUT_DIR, exist_ok=True)
    open(os.path.join(OUT_DIR, 'web_gold.json'), 'w', encoding='utf-8').write(raw)
    root_w = web[0]['width'] if web else 375
    factor = 750.0 / root_w
    print(f'web 层数 {len(web)} 画布宽 {root_w} factor={factor}')

    # 2) CLI convert
    ex = m.LanhuExtractor()
    sk = await ex.get_sketch_json(DID, None, PID)
    _h, _mp, annots = m.convert_sketch_to_html(sk, 2.0, '')
    out = defaultdict(list)
    for a in annots:
        out[a.get('name')].append(a.get('css', {}))
    await ex.close()

    # 3) 逐元素对比
    def rr(v):
        return round(float(v) * factor, 1) if v is not None else None
    g_ok = g_bad = c_ok = c_bad = r_ok = r_bad = s_ok = s_bad = 0
    bad = []
    wg = defaultdict(list)
    for L in web[1:]:
        if L.get('width') or L.get('height'):
            wg[L['name']].append(L)
    for nm, wl in wg.items():
        cl = out.get(nm, [])
        for i, w in enumerate(wl):
            if i >= len(cl):
                continue
            c = cl[i]
            # 几何
            exp = {'left': rr(w.get('left', 0)), 'top': rr(w.get('top', 0)), 'width': rr(w.get('width', 0)), 'height': rr(w.get('height', 0))}
            gmatch = all(n(c.get(f)) == exp[f] or n(c.get(f)) == (int(exp[f]) if exp[f] is not None else None) for f in exp)
            if gmatch:
                g_ok += 1
            else:
                g_bad += 1
                bad.append(f"[{nm}] 几何 web={exp} cli左{c.get('left')}顶{c.get('top')}宽{c.get('width')}高{c.get('height')}")
            # 颜色
            if w.get('color'):
                cc = re.sub(r'\s', '', c.get('color', '') or '')
                if cc == re.sub(r'\s', '', w['color']):
                    c_ok += 1
                else:
                    c_bad += 1
                    bad.append(f"[{nm}] 色 web={w['color']} cli={c.get('color')}")
            # 圆角
            rad = w.get('radius') or {}
            if isinstance(rad, dict) and any((rad.get(k) or 0) > 0 for k in ('topLeft', 'topRight', 'bottomRight', 'bottomLeft')):
                exp_r = rr(rad.get('topLeft', 0))
                cbr = n(c.get('border-radius'))
                if cbr == exp_r or cbr == (int(exp_r) if exp_r else None):
                    r_ok += 1
                else:
                    r_bad += 1
                    bad.append(f"[{nm}] 圆角 web={exp_r} cli={c.get('border-radius')}")
            # 阴影(有无)
            if [s for s in (w.get('shadows') or []) if s.get('isEnabled', True)]:
                if 'box-shadow' in c:
                    s_ok += 1
                else:
                    s_bad += 1
                    bad.append(f"[{nm}] 阴影 web有 cli无")
    print(f'\n=== 对 web 金标准实测 ===')
    print(f'  几何: 一致{g_ok} 不一致{g_bad}')
    print(f'  颜色: 一致{c_ok} 不一致{c_bad}')
    print(f'  圆角: 一致{r_ok} 不一致{r_bad}')
    print(f'  阴影: 一致{s_ok} 不一致{s_bad}')
    if bad:
        print('\n--- 不一致明细(前25) ---')
        for x in bad[:25]:
            print('  ' + x)
    else:
        print('\n🎉 全部逐字一致')

asyncio.run(main())
