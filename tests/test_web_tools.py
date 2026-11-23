"""网络搜索工具测试"""

import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def make_web_tools(monkeypatch, tmp_path):
    if importlib.util.find_spec("aacode") is None:
        # Source checkouts can have a directory name other than aacode.
        (tmp_path / "aacode").symlink_to(Path(__file__).resolve().parents[1])
        monkeypatch.syspath_prepend(str(tmp_path))

    from aacode.config import settings
    from aacode.tools.web_tools import WebTools

    monkeypatch.setattr(settings.tools, "search_api_url", None)
    monkeypatch.setattr(settings.tools, "search_api_key", None)
    monkeypatch.setattr(settings.tools, "enable_web_search", True)
    monkeypatch.setattr(settings.tools, "enable_fallback_scrape", False)
    for name in (
        "SEARCHXNG_URL",
        "BRAVE_API_KEY",
        "GOOGLE_API_KEY",
        "BING_API_KEY",
        "SERPAPI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    def make():
        tools = WebTools(tmp_path, None)
        tools.session = MagicMock(closed=False)
        return tools

    return make


def response(status, payload):
    context = MagicMock()
    context.__aenter__.return_value.status = status
    context.__aenter__.return_value.json = AsyncMock(return_value=payload)
    return context


@pytest.mark.asyncio
async def test_monid_search_with_only_monid_key(monkeypatch, make_web_tools):
    monkeypatch.setenv("MONID_API_KEY", "test-key")
    tools = make_web_tools()
    tools.session.post.return_value = response(
        200,
        {
            "status": "COMPLETED",
            "output": {
                "results": [
                    {"title": "示例", "link": "https://example.com", "snippet": "摘要"}
                ]
            },
        },
    )

    result = await tools.search_web("中文查询", engine="monid", max_results=3)

    tools.session.post.assert_called_once()
    args, kwargs = tools.session.post.call_args
    assert args == ("https://api.monid.ai/v1/run",)
    assert kwargs["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json; charset=utf-8",
    }
    assert "中文查询".encode("utf-8") in kwargs["data"]
    assert json.loads(kwargs["data"]) == {
        "provider": "search1api",
        "endpoint": "/search",
        "input": {"body": {"query": "中文查询", "max_results": 3}},
    }
    assert result == {
        "success": True,
        "engine": "monid",
        "query": "中文查询",
        "results": [
            {
                "title": "示例",
                "url": "https://example.com",
                "content": "摘要",
                "engine": "monid",
                "score": 0,
            }
        ],
        "total_results": 1,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("monid_key", [None, "test-key"])
async def test_monid_preserves_auto_engine(monkeypatch, make_web_tools, monid_key):
    if monid_key is None:
        monkeypatch.delenv("MONID_API_KEY", raising=False)
    else:
        monkeypatch.setenv("MONID_API_KEY", monid_key)
    monkeypatch.setenv("SEARCHXNG_URL", "http://localhost:8080")
    tools = make_web_tools()
    searxng = AsyncMock(return_value={"success": True, "engine": "searxng"})
    monkeypatch.setattr(tools, "_search_searxng", searxng)

    assert (await tools.search_web("query"))["engine"] == "searxng"
    searxng.assert_awaited_once_with("query", 10, True, 8)
    tools.session.post.assert_not_called()
    if monid_key is None:
        assert "monid" not in tools.search_engines


@pytest.mark.asyncio
async def test_monid_polls_and_handles_provider_error(monkeypatch, make_web_tools):
    from aacode.tools import web_tools as web_module

    monkeypatch.setenv("MONID_API_KEY", "test-key")
    tools = make_web_tools()
    monkeypatch.setattr(web_module.asyncio, "sleep", AsyncMock())
    tools.session.post.return_value = response(202, {"runId": "run-123"})
    tools.session.get.side_effect = [
        response(200, {"status": "RUNNING"}),
        response(
            200,
            {
                "status": "COMPLETED",
                "providerResponse": {
                    "httpStatus": 429,
                    "error": {"message": "Rate limited"},
                },
            },
        ),
    ]

    assert await tools.search_web("query", engine="monid") == {
        "success": False,
        "error": "Search1API HTTP 429",
        "query": "query",
    }
    assert [call.args for call in tools.session.get.call_args_list] == [
        ("https://api.monid.ai/v1/runs/run-123",),
        ("https://api.monid.ai/v1/runs/run-123",),
    ]
