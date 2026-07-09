#!/usr/bin/env python3
"""蓝湖设计图 层覆盖诊断工具(调试用,不影响正常 analyze,平时零开销)。
用法: python tools/debug_coverage.py <设计名或序号> <pid>  (或设环境变量 LANHU_PID)
分类: ✅已输出 / 🔵原始无内容 / ⚪合理不输出(mask·状态栏·根画布·纯容器) /
      🔴可疑丢失(有内容却没输出=真bug信号,非0才查) + 圆角/阴影/渐变覆盖率。"""
import asyncio
import os
import sys

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


def diagnose(sketch_json):
    _h, _mp, annots = m.convert_sketch_to_html(sketch_json, 2.0, '')
    outc = {}
    for a in annots:
        outc[a.get('name')] = outc.get(a.get('name'), 0) + 1
    seen = {}
    root = sketch_json.get('artboard') or sketch_json.get('board') or {}
    rname = root.get('name')
    stat = {'output': 0, 'no_visual': 0, 'invisible': 0, 'zero': 0, 'container': 0, 'mask': 0, 'statusbar': 0, 'root': 0, 'dup': 0, 'SUSPICIOUS': []}
    fx = {'rad': 0, 'sh': 0, 'gr': 0}

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
            fx['rad'] += 1
        if hs:
            fx['sh'] += 1
        if any('gradient' in str(f.get('type', '')).lower() for f in (st.get('fills') or []) if isinstance(f, dict)):
            fx['gr'] += 1
        if seen.get(nm, 0) < outc.get(nm, 0):
            seen[nm] = seen.get(nm, 0) + 1
            stat['output'] += 1
        elif node.get('visible') is False:
            stat['invisible'] += 1
        elif w == 0 and h == 0:
            stat['zero'] += 1
        elif node.get('isMask'):
            stat['mask'] += 1
        elif is_root or nm == rname:
            stat['root'] += 1
        elif nm in STATUSBAR:
            stat['statusbar'] += 1
        elif ty in CONTAINER and not vis:
            stat['container'] += 1
        elif not vis:
            stat['no_visual'] += 1
        elif outc.get(nm, 0) >= 1:
            stat['dup'] += 1
        else:
            stat['SUSPICIOUS'].append(f'{nm}({ty}) fill={hf} shadow={hs} radius={hr}')
        for c in (node.get('layers') or []):
            walk(c)
    walk(root, True)
    o_rad = sum(1 for a in annots if 'border-radius' in a.get('css', {}))
    o_sh = sum(1 for a in annots if 'box-shadow' in a.get('css', {}))
    o_gr = sum(1 for a in annots if 'gradient' in str(a.get('css', {}).get('background', '')))
    return stat, fx, len(annots), o_rad, o_sh, o_gr


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    name = sys.argv[1]
    pid = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PID
    if not pid:
        print('用法: python tools/debug_coverage.py <设计名或序号> <pid>  (或设环境变量 LANHU_PID)')
        return
    ex = m.LanhuExtractor()
    res = await m.lanhu_get_designs(f'https://lanhuapp.com/web/#/item/project/stage?pid={pid}')
    designs = [d for d in (res.get('designs') or []) if d.get('id')]
    target = None
    if name.isdigit():
        target = next((d for d in designs if str(d.get('index')) == name), None)
    if target is None:
        target = next((d for d in designs if d.get('name') == name), None)
    if target is None:
        print('未找到,可用: ' + ', '.join(f"{d.get('index')}={d.get('name')}" for d in designs[:10]))
        await ex.close()
        return
    sk = await ex.get_sketch_json(target['id'], None, pid)
    stat, fx, n, o_rad, o_sh, o_gr = diagnose(sk)
    print(f'\n=== 覆盖诊断: [{target.get("index")}] {target.get("name")} ===')
    print(f'  输出{n} 命中原始{stat["output"]}')
    print(f'  合理不输出: 纯容器{stat["container"]} mask{stat["mask"]} 状态栏{stat["statusbar"]} 根{stat["root"]} 重名叠放{stat["dup"]} 不可见{stat["invisible"]} 尺寸0{stat["zero"]} 无内容{stat["no_visual"]}')
    ns = len(stat['SUSPICIOUS'])
    print(f'  {"🔴" if ns else "🟢"}可疑丢失(真bug信号): {ns}')
    for s in stat['SUSPICIOUS'][:25]:
        print('       ' + s)
    print(f'  属性覆盖: 圆角{fx["rad"]}→{o_rad} 阴影{fx["sh"]}→{o_sh} 渐变{fx["gr"]}→{o_gr}')
    await ex.close()

asyncio.run(main())
