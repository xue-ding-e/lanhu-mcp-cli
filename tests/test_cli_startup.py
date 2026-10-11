"""Guard CLI startup against browser/MCP imports and preserve MCP behavior."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _probe(code):
    result = subprocess.run(
        [sys.executable, "-B", "-X", "utf8", "-c", code],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.mark.parametrize("args", [
    ["--help"], ["designs", "--help"], ["tools"],
])
def test_cli_metadata_works_without_site_packages(args):
    result = subprocess.run(
        [sys.executable, "-B", "-S", str(ROOT / "lanhu_cli.py"), *args],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=10,
    )
    assert result.returncode == 0, result.stderr
    if args == ["tools"]:
        assert "designs" in json.loads(result.stdout)
    else:
        assert "usage: lanhu" in result.stdout


def test_core_calls_do_not_import_mcp_or_playwright():
    _probe("""
import asyncio, importlib.abc, os, sys
class BlockHeavy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'fastmcp', 'mcp', 'playwright'}:
            raise AssertionError('Unexpected heavy import: ' + fullname)
sys.meta_path.insert(0, BlockHeavy())
import lanhu_mcp_server as core
os.environ['LANHU_USER_NAME'] = 'startup-test'
os.environ['LANHU_USER_ROLE'] = 'tester'
assert core.get_user_info(None) == ('startup-test', 'tester')
guide = asyncio.run(core.lanhu_get_workflow_guide(analysis_mode='tester'))
assert 'STAGE 1' in guide
import lanhu_cli as cli
image = core.Image(path='screenshot.png')
assert cli._conv({'items': [image, b'123']}) == {
    'items': [{'image_path': 'screenshot.png'}, '<bytes 3B omitted>']
}
""")


def test_mcp_registration_and_context_injection():
    _probe("""
import asyncio, lanhu_cli as cli, lanhu_mcp_server as core
from fastmcp import Client, FastMCP
async def check():
    image_before_mcp = core.Image(path='screenshot.png')
    server = core.mcp
    assert isinstance(server, FastMCP)
    assert server is core.mcp
    assert cli._conv(image_before_mcp) == {'image_path': 'screenshot.png'}
    async with Client(server) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools} == {name for name, _ in cli.COMMANDS.values()}
        assert all('ctx' not in t.inputSchema['properties'] for t in tools)
        result = await client.call_tool(
            'lanhu_get_workflow_guide', {'analysis_mode': 'tester'},
        )
        assert 'STAGE 1' in result.content[0].text
asyncio.run(check())
""")


def test_screenshot_cache_does_not_load_browser(tmp_path):
    import lanhu_mcp_server as core
    import asyncio
    import importlib.abc

    (tmp_path / ".screenshot_cache.json").write_text(
        json.dumps({"version_id": "v1"}), encoding="utf-8",
    )
    (tmp_path / "home.png").write_bytes(b"cached-png")
    (tmp_path / "home_annotations.json").write_text("[]", encoding="utf-8")

    class BlockBrowser(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith("playwright"):
                raise AssertionError("Cached screenshot loaded browser")
    blocker = BlockBrowser()
    sys.meta_path.insert(0, blocker)
    try:
        results = asyncio.run(core.screenshot_page_internal(
            str(tmp_path), ["home"], str(tmp_path),
            return_base64=False, version_id="v1",
        ))
    finally:
        sys.meta_path.remove(blocker)
    assert len(results) == 1
    assert results[0]["from_cache"] is True
    assert results[0]["screenshot_path"] == str(tmp_path / "home.png")


def test_screenshot_server_is_ready_without_fixed_sleep(tmp_path):
    import asyncio
    import lanhu_mcp_server as core
    from playwright.async_api import async_playwright

    async def check():
        async with async_playwright() as playwright:
            if not Path(playwright.chromium.executable_path).exists():
                pytest.skip("Chromium is not installed")
        resource_dir = tmp_path / "resource"
        resource_dir.mkdir()
        (resource_dir / "home.html").write_text(
            "<html><body><h1>startup screenshot test</h1></body></html>",
            encoding="utf-8",
        )
        results = await core.screenshot_page_internal(
            str(resource_dir), ["home"], str(tmp_path / "output"),
            return_base64=False, version_id="v1",
        )
        assert len(results) == 1
        assert results[0]["success"] is True, results[0]
        assert "startup screenshot test" in results[0]["page_text"]
        assert Path(results[0]["screenshot_path"]).read_bytes().startswith(b"\x89PNG")
    asyncio.run(check())
