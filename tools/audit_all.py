#!/usr/bin/env python3
"""全项目覆盖审计:遍历所有设计图逐层归因,证明'零真丢失'是否普遍(分模块+归因)。
用法: python tools/audit_all.py <pid>  (或设环境变量 LANHU_PID)"""
import asyncio
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo 根,保证任意 cwd 下能 import
import lanhu_mcp_server as m

DEFAULT_PID = os.environ.get('LANHU_PID', '')
CONTAINER = {'layerSection', 'symbolInstence', 'artboard', 'groupLayer'}
STATUSBAR = {'Cellular-Connection-path', 'Wifi-path', 'status-bar', 'HomeIndicator', 'Border', 'Cap', 'Frame 8', 'Frame 9'}


def _fill(node, st):
    return bool((node.get('fill') or {}).get('color')) or any(isinstance(f, dict) and f.get('isEnabled', True) for f in (st.get('fills') or []))


def _shadow(st):
    return any(isinstance(s, dict) and s.get('isEnabled', True) for s in (st.get('shadows') or []))


def _radius(node):
    r = node.get('radius') or {}
    return isinstance(r, dict) and any((r.get(k) or 0) > 0 for k in ('topLeft', 'topRight', 'bottomRight', 'bottomLeft'))


def diagnose(sk):
    try:
        _h, _mp, annots = m.convert_sketch_to_html(sk, 2.0, '')
    except Exception as e:
        return None, str(e)
    outc = Counter(a.get('name') for a in annots)
    seen = Counter()
    root = sk.get('artboard') or sk.get('board') or {}
    rname = root.get('name')
    res = {'out': 0, 'susp': [], 'rad_raw': 0, 'sh_raw': 0, 'gr_raw': 0}

    def walk(node, is_root=False):
        if not isinstance(node, dict):
            return
        nm, ty = node.get('name', ''), node.get('type', '')
        st = node.get('style') or {}
        fr = node.get('frame') or {}
        w = fr.get('width', node.get('width', 0)) or 0
        h = fr.get('height', node.get('height', 0)) or 0
        hf, hs, hr = _fill(node, st), _shadow(st), _radius(node)
        ht = ty == 'textLayer' and (node.get('textInfo') or node.get('text'))
        imgs = node.get('images') or {}
        hsl = bool(imgs.get('png_xxxhd') or imgs.get('svg'))
        vis = hf or hs or hr or bool(ht) or hsl or bool(st.get('borders'))
        if hr:
            res['rad_raw'] += 1
        if hs:
            res['sh_raw'] += 1
        if any('gradient' in str(f.get('type', '')).lower() for f in (st.get('fills') or []) if isinstance(f, dict)):
            res['gr_raw'] += 1
        if seen[nm] < outc[nm]:
            seen[nm] += 1
            res['out'] += 1
        elif node.get('visible') is False or (w == 0 and h == 0) or node.get('isMask') \
                or is_root or nm == rname or nm in STATUSBAR or (ty in CONTAINER and not vis) or not vis:
            pass
        elif outc[nm] >= 1:
            pass  # 重名叠放/mask多余实例(视觉不影响)
        else:
            res['susp'].append(f'{nm}({ty})')
        for c in (node.get('layers') or []):
            walk(c)
    walk(root, True)
    res['rad_out'] = sum(1 for a in annots if 'border-radius' in a.get('css', {}))
    res['sh_out'] = sum(1 for a in annots if 'box-shadow' in a.get('css', {}))
    res['n'] = len(annots)
    return res, None


def module_of(name):
    n = name.replace('小说-商城-', '').replace('小说-', '')
    return n.split('-')[0][:8] if n else '其他'


async def main():
    pid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PID
    if not pid:
        print('用法: python tools/audit_all.py <pid>  (或设环境变量 LANHU_PID)')
        return
    ex = m.LanhuExtractor()
    res = await m.lanhu_get_designs(f'https://lanhuapp.com/web/#/item/project/stage?pid={pid}')
    designs = [d for d in (res.get('designs') or []) if d.get('id')]
    print(f'全项目 {len(designs)} 图,逐张审计中...')
    mod = defaultdict(lambda: {'imgs': 0, 'susp': 0, 'elem': 0})
    all_susp = Counter()
    rad_bad, sh_bad = [], []
    errs = []
    tot_elem = tot_susp = ok_imgs = 0
    for d in designs:
        try:
            sk = await ex.get_sketch_json(d['id'], None, pid)
        except Exception as e:
            errs.append(f"{d.get('name')}: {e}")
            continue
        r, err = diagnose(sk)
        if err:
            errs.append(f"{d.get('name')}: {err}")
            continue
        mk = module_of(d.get('name', ''))
        mod[mk]['imgs'] += 1
        mod[mk]['susp'] += len(r['susp'])
        mod[mk]['elem'] += r['n']
        tot_elem += r['n']
        tot_susp += len(r['susp'])
        for s in r['susp']:
            all_susp[s.split('(')[0]] += 1
        if not r['susp']:
            ok_imgs += 1
        nm = (d.get('name') or '')[:20]
        if r['rad_raw'] != r['rad_out']:
            rad_bad.append(f"[{d.get('index')}]{nm} {r['rad_raw']}->{r['rad_out']}")
        if r['sh_raw'] != r['sh_out']:
            sh_bad.append(f"[{d.get('index')}]{nm} {r['sh_raw']}->{r['sh_out']}")
    await ex.close()
    print(f'\n=== {len(designs)-len(errs)}图 总{tot_elem}元素 ===')
    print(f'零可疑丢失图: {ok_imgs}/{len(designs)-len(errs)} | 可疑丢失总数: {tot_susp}')
    print('--- 可疑丢失归因 ---')
    if all_susp:
        for nm, c in all_susp.most_common(30):
            print(f'  {nm} x{c}')
    else:
        print('  无(全项目零真丢失)')
    print(f'--- 属性偏差(重名叠放/mask多余实例,非bug): 圆角{len(rad_bad)}图 阴影{len(sh_bad)}图 ---')
    print('--- 分模块 ---')
    for mk in sorted(mod, key=lambda k: -mod[k]['imgs']):
        v = mod[mk]
        print(f'  {mk} {v["imgs"]}图 {v["elem"]}元素 可疑{v["susp"]}')

asyncio.run(main())
