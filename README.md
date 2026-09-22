# lanhu-mcp-cli

由 [xue-ding-e](https://github.com/xue-ding-e) 维护的蓝湖 MCP 服务与 CLI，用于读取需求文档、设计稿、切图标注和原型交互关系。

项目地址：[xue-ding-e/lanhu-mcp-cli](https://github.com/xue-ding-e/lanhu-mcp-cli)。

## 功能

- 枚举项目中的产品文档、原型页面和 UI 设计稿。
- 提取页面文本、截图、设计元素及 CSS 标注。
- 下载切图，读取原型热区和页面跳转关系。
- 通过 CLI 输出 JSON，图片返回本地路径，便于脚本和 AI 工具继续处理。
- MCP 与 CLI 共用服务核心；提供团队成员查询和留言板操作。

## Windows 本地安装

需要 Python 3.10 或更高版本，以及可访问目标项目的蓝湖账号。

```powershell
git clone https://github.com/xue-ding-e/lanhu-mcp-cli.git
cd lanhu-mcp-cli
python -m venv venv
.\venv\Scripts\python.exe -m pip install -e .
.\venv\Scripts\python.exe -m playwright install chromium
```

首次配置时，将 `.env.example` 复制为 `.env`，填写 `LANHU_COOKIE`。获取方式见 [Cookie 配置说明](GET-COOKIE-TUTORIAL.md)。已有 `.env` 时直接编辑，避免覆盖本地配置。

Cookie 仅保存在本地环境中；`.env`、`data/`、`logs/` 和虚拟环境已被 Git 忽略。

## CLI

```powershell
.\lanhu.ps1 tools
.\lanhu.ps1 designs "<蓝湖项目 URL>"
.\lanhu.ps1 analyze-design "<蓝湖项目 URL>" "<设计稿名称>"
.\lanhu.ps1 slices "<蓝湖项目 URL>" "<设计稿名称>"
.\lanhu.ps1 interactions "<蓝湖项目 URL>"
.\lanhu.ps1 analyze-design -h
```

也可直接使用 `venv` 中的 Python 执行 `lanhu_cli.py`。macOS / Linux 创建 `venv` 后，使用 `venv/bin/python` 安装依赖和执行相同命令。

## MCP 配置

将以下路径替换为本机仓库绝对路径。服务会读取仓库目录下的 `.env`：

```json
{
  "mcpServers": {
    "lanhu-mcp-cli": {
      "command": "D:/path/to/lanhu-mcp-cli/venv/Scripts/python.exe",
      "args": ["D:/path/to/lanhu-mcp-cli/lanhu_mcp_server.py"],
      "env": {
        "MCP_TRANSPORT": "stdio"
      }
    }
  }
}
```

HTTP / Docker 部署见 [DEPLOY.md](DEPLOY.md)。

## 文档与反馈

- [使用示例](DEMO.md)
- [安装指南](ai-install-guide.md)
- [开发说明](CONTRIBUTING.md)
- [更新记录](CHANGELOG.md)
- [问题反馈](https://github.com/xue-ding-e/lanhu-mcp-cli/issues)

## 许可证

采用 MIT 许可证，保留原始版权声明，详见 [LICENSE](LICENSE)。本工具独立维护，不代表蓝湖官方。
