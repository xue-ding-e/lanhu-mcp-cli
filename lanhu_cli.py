#!/usr/bin/env python3
"""
lanhu CLI — 蓝湖工具的 agent 原生命令行(复用 lanhu_mcp_server 同一核心,MCP 保留为兜底)。

设计(agent 原生定案):
- CLI-per-command:蓝湖是无状态 HTTP API 包装,每命令独立进程,无 daemon/无持久连接。
- 紧凑返回:stdout 一行 JSON;fastmcp Image 一律转 {"image_path": 本地路径}(截图本已落盘,agent 用 Read 看图)。
- 渐进披露:`lanhu tools` 列 名称+一句话;`lanhu <cmd> -h` 才展开参数——不预载全量 schema。

用法: venv\\Scripts\\python.exe lanhu_cli.py <命令> [参数]  (或经 lanhu.cmd 垫片)
"""
import argparse
import asyncio
import json
import re
import sys

# Windows GBK 控制台会让 emoji/中文 JSON 打印崩溃,强制 utf-8
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import lanhu_mcp_server as m

try:
    from fastmcp.utilities.types import Image as _FmImage
except ImportError:
    _FmImage = None


def _conv(o):
    """结果规整:Image→image_path;bytes→占位;其余递归。"""
    if _FmImage is not None and isinstance(o, _FmImage):
        p = getattr(o, 'path', None)
        return {'image_path': str(p)} if p else {'image': '<inline-bytes-omitted>'}
    if isinstance(o, bytes):
        return f'<bytes {len(o)}B omitted>'
    if isinstance(o, dict):
        return {k: _conv(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_conv(v) for v in o]
    return o


def _out(result):
    print(json.dumps(_conv(result), ensure_ascii=False, default=str))


def _extract_elements(result):
    """从 analyze-design 返回的 HTML 文本解析出结构化元素数组。

    为什么:原始返回把每个元素的 data-css(1:1 抄样式的核心)埋在一大坨 HTML 字符串里,
    经 JSON 序列化后引号变 \\" ——agent 想用样式得先 JSON.parse 再正则反转义,反 agent 原生。
    这里 CLI 侧直接解析成 [{name, css:{...}, text}],agent 拿到就能逐元素抄,零转义零正则。
    """
    text = ''.join(x for x in result if isinstance(x, str))
    out = []
    # <div/img class=elN title="X"(或无引号) data-css="k: v; ...">text
    for mt in re.finditer(r'\btitle=(?:"([^"]*)"|([^\s>]+))\s+data-css="([^"]*)"([^>]*)>?([^<]*)', text):
        name = (mt.group(1) if mt.group(1) is not None else mt.group(2)) or ''
        css_str = mt.group(3).replace('&quot;', '"')
        tail = mt.group(4) or ''
        txt = (mt.group(5) or '').replace('&lt;', '<').replace('&gt;', '>').strip()
        css = {}
        for pair in css_str.split(';'):
            pair = pair.strip()
            if ':' in pair:
                k, v = pair.split(':', 1)
                css[k.strip()] = v.strip()
        el = {'name': name, 'css': css}
        msrc = re.search(r'\bsrc="([^"]*)"', tail)
        if msrc:
            el['slice_src'] = msrc.group(1)  # 切图元素的图片地址
        if txt:
            el['text'] = txt
        out.append(el)
    return out


def _split(s):
    """逗号分隔转列表('首页,登录'→['首页','登录']);无逗号原样(含 'all')。"""
    if s is None:
        return None
    return [x.strip() for x in s.split(',')] if ',' in s else s


def _run(coro):
    return asyncio.run(coro)


# 命令注册表:名称 -> (工具函数名, 一句话)。tools 子命令用它做渐进披露。
COMMANDS = {
    'resolve-invite': ('lanhu_resolve_invite_link', '邀请/分享链接 → 真实项目URL'),
    'docs': ('lanhu_list_product_documents', '列项目下所有产品文档(PRD/原型)'),
    'pages': ('lanhu_get_pages', '取PRD/原型文档的页面列表(分析前先调)'),
    'analyze-page': ('lanhu_get_ai_analyze_page_result', '分析PRD页面(文本+截图路径)'),
    'designs': ('lanhu_get_designs', '取UI设计图列表(分析设计前先调)'),
    'analyze-design': ('lanhu_get_ai_analyze_design_result', '分析UI设计图(视觉+HTML代码)'),
    'slices': ('lanhu_get_design_slices', '取单张设计图的切图/标注(含精确CSS)'),
    'interactions': ('lanhu_get_prototype_interactions', '读设计态原型热区跳转关系'),
    'workflow-guide': ('lanhu_get_workflow_guide', '取四阶段需求分析工作流指引(按需一次)'),
    'members': ('lanhu_get_members', '项目协作者列表'),
    'say': ('lanhu_say', '发留言到团队留言板'),
    'say-list': ('lanhu_say_list', '查留言(可过滤/正则搜索/限量)'),
    'say-detail': ('lanhu_say_detail', '留言详情(支持批量)'),
    'say-edit': ('lanhu_say_edit', '编辑留言'),
    'say-delete': ('lanhu_say_delete', '删除留言'),
}


def build_parser():
    p = argparse.ArgumentParser(
        prog='lanhu',
        description='蓝湖 CLI(agent 原生)。`lanhu tools` 看命令清单;`lanhu <命令> -h` 看参数。',
    )
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('tools', help='列出所有命令(名称+一句话,渐进披露)')

    s = sub.add_parser('resolve-invite', help=COMMANDS['resolve-invite'][1])
    s.add_argument('invite_url', help='邀请链接,如 https://lanhuapp.com/link/#/invite?sid=xxx')

    s = sub.add_parser('docs', help=COMMANDS['docs'][1])
    s.add_argument('url', help='项目URL(含tid+pid,docId可省)')

    s = sub.add_parser('pages', help=COMMANDS['pages'][1])
    s.add_argument('url', help='带docId的文档URL')

    s = sub.add_parser('analyze-page', help=COMMANDS['analyze-page'][1])
    s.add_argument('url', help='带docId的文档URL')
    s.add_argument('page_names', help="页面名:'all' / 单名 / 逗号分隔多名")
    s.add_argument('--mode', default='full', choices=['full', 'text_only'], help='full=图+文(默认);text_only=快速全局文本扫描')
    s.add_argument('--analysis-mode', default='developer', choices=['developer', 'tester', 'explorer'], help='分析视角(默认developer)')

    s = sub.add_parser('designs', help=COMMANDS['designs'][1])
    s.add_argument('url', help='设计项目URL(无docId,如 stage?pid=xxx)')

    s = sub.add_parser('analyze-design', help=COMMANDS['analyze-design'][1])
    s.add_argument('url', help='设计项目URL(无docId)')
    s.add_argument('design_names', help="设计名/序号:'all' / 单个 / 逗号分隔")

    s = sub.add_parser('slices', help=COMMANDS['slices'][1])
    s.add_argument('url', help='设计项目URL(无docId)')
    s.add_argument('design_name', help='精确单个设计名(不支持all)')
    s.add_argument('--no-metadata', action='store_true', help='不含颜色/阴影等元数据')

    s = sub.add_parser('interactions', help=COMMANDS['interactions'][1])
    s.add_argument('url', help='带image_id时返回该图交互;否则全项目')

    s = sub.add_parser('workflow-guide', help=COMMANDS['workflow-guide'][1])
    s.add_argument('--analysis-mode', default='developer', choices=['developer', 'tester', 'explorer'])

    s = sub.add_parser('members', help=COMMANDS['members'][1])
    s.add_argument('url', help='项目URL(含tid+pid)')

    s = sub.add_parser('say', help=COMMANDS['say'][1])
    s.add_argument('url', help='项目URL(含tid+pid)')
    s.add_argument('summary', help='留言标题')
    s.add_argument('content', help='留言内容')
    s.add_argument('--mentions', help='@人名,逗号分隔(必须具体人名)')
    s.add_argument('--type', dest='message_type', choices=['normal', 'task', 'question', 'urgent', 'knowledge'], help='留言类型')

    s = sub.add_parser('say-list', help=COMMANDS['say-list'][1])
    s.add_argument('--url', help="项目URL或'all'(默认所有项目)")
    s.add_argument('--type', dest='filter_type', choices=['normal', 'task', 'question', 'urgent', 'knowledge'])
    s.add_argument('--search', dest='search_regex', help="正则搜索,如 '测试|退款'")
    s.add_argument('--limit', type=int, help='限量(防上下文爆炸)')

    s = sub.add_parser('say-detail', help=COMMANDS['say-detail'][1])
    s.add_argument('message_ids', help='消息ID:单个或逗号分隔')
    s.add_argument('--url', help='项目URL(传则自动解析项目)')
    s.add_argument('--project-id', help='项目ID(不传url时用)')

    s = sub.add_parser('say-edit', help=COMMANDS['say-edit'][1])
    s.add_argument('url', help='项目URL')
    s.add_argument('message_id', help='消息ID')
    s.add_argument('--summary', help='新标题(不传不改)')
    s.add_argument('--content', help='新内容(不传不改)')
    s.add_argument('--mentions', help='新@列表,逗号分隔')

    s = sub.add_parser('say-delete', help=COMMANDS['say-delete'][1])
    s.add_argument('url', help='项目URL')
    s.add_argument('message_id', help='消息ID')

    return p


def main():
    args = build_parser().parse_args()
    c = args.cmd

    if c == 'tools':
        _out({name: desc for name, (_, desc) in COMMANDS.items()})
        return

    if c == 'resolve-invite':
        _out(_run(m.lanhu_resolve_invite_link(args.invite_url)))
    elif c == 'docs':
        _out(_run(m.lanhu_list_product_documents(args.url)))
    elif c == 'pages':
        _out(_run(m.lanhu_get_pages(args.url)))
    elif c == 'analyze-page':
        _out(_run(m.lanhu_get_ai_analyze_page_result(
            args.url, _split(args.page_names), mode=args.mode, analysis_mode=args.analysis_mode)))
    elif c == 'designs':
        _out(_run(m.lanhu_get_designs(args.url)))
    elif c == 'analyze-design':
        result = _run(m.lanhu_get_ai_analyze_design_result(args.url, _split(args.design_names)))
        elements = _extract_elements(result)
        # elements=结构化直读(抄样式主力);raw=完整原始(含设计token/切图下载映射表/截图路径,兜底)
        _out({'element_count': len(elements), 'elements': elements, 'raw': _conv(result)})
    elif c == 'slices':
        _out(_run(m.lanhu_get_design_slices(args.url, args.design_name, include_metadata=not args.no_metadata)))
    elif c == 'interactions':
        _out(_run(m.lanhu_get_prototype_interactions(args.url)))
    elif c == 'workflow-guide':
        _out(_run(m.lanhu_get_workflow_guide(analysis_mode=args.analysis_mode)))
    elif c == 'members':
        _out(_run(m.lanhu_get_members(args.url)))
    elif c == 'say':
        _out(_run(m.lanhu_say(args.url, args.summary, args.content,
                              mentions=_split(args.mentions), message_type=args.message_type)))
    elif c == 'say-list':
        _out(_run(m.lanhu_say_list(url=args.url, filter_type=args.filter_type,
                                   search_regex=args.search_regex, limit=args.limit)))
    elif c == 'say-detail':
        _out(_run(m.lanhu_say_detail(_split(args.message_ids), url=args.url, project_id=args.project_id)))
    elif c == 'say-edit':
        _out(_run(m.lanhu_say_edit(args.url, args.message_id, summary=args.summary,
                                   content=args.content, mentions=_split(args.mentions))))
    elif c == 'say-delete':
        _out(_run(m.lanhu_say_delete(args.url, args.message_id)))


if __name__ == '__main__':
    main()
