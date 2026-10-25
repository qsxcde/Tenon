"""web/todo 原子工具行为测试(离线:fetcher/searcher 均注入假实现)。"""

from __future__ import annotations

import pytest

from tenon.tools.atomic import TodoTool, WebFetchTool, WebSearchTool
from tenon.tools.atomic.todo import MAX_TODOS, TodoItem, TodoState


def _invoke(tool, **kwargs):
    return tool.invoke(tool.Args(**kwargs))


def _fake_fetcher(body: str):
    calls: list[str] = []

    def fetch(url: str) -> str:
        calls.append(url)
        return body

    return fetch, calls


# -- web_fetch ---------------------------------------------------------------


def test_web_fetch_returns_governed_text_with_metadata():
    fetch, calls = _fake_fetcher("hello web")
    tool = WebFetchTool(fetcher=fetch)

    out = _invoke(tool, url="https://example.com")

    assert "hello web" in out
    assert calls == ["https://example.com"]
    assert out.output_metadata["source"] == "web_fetch"
    assert out.output_metadata["url"] == "https://example.com"
    assert out.output_metadata["completeness"] == "complete"


def test_web_fetch_rejects_non_http_schemes():
    fetch, calls = _fake_fetcher("x")
    tool = WebFetchTool(fetcher=fetch)

    with pytest.raises(ValueError, match="仅支持 http/https"):
        _invoke(tool, url="file:///etc/passwd")
    assert calls == []


def test_web_fetch_wraps_fetcher_error():
    def fetch(url: str) -> str:
        raise OSError("connection refused")

    tool = WebFetchTool(fetcher=fetch)
    with pytest.raises(ValueError, match="抓取失败"):
        _invoke(tool, url="https://example.com")


def test_web_fetch_truncates_large_content():
    fetch, _ = _fake_fetcher("x" * 200_000)
    tool = WebFetchTool(fetcher=fetch)

    out = _invoke(tool, url="https://example.com")

    assert out.output_metadata["completeness"] == "truncated"
    assert out.output_metadata["total_bytes"] > out.output_metadata["shown_bytes"]


# -- web_search --------------------------------------------------------------


def test_web_search_without_searcher_returns_unavailable():
    tool = WebSearchTool()

    out = _invoke(tool, query="tenon")

    assert "不可用" in out and "未配置搜索提供方" in out


def test_web_search_renders_numbered_results_with_limit():
    def searcher(query: str, limit: int) -> list[str]:
        assert query == "tenon" and limit == 2
        return ["a https://a.example", "b https://b.example", "c https://c.example"]

    tool = WebSearchTool(searcher=searcher)
    out = _invoke(tool, query="tenon", limit=2)

    assert "1. a https://a.example" in out
    assert "2. b https://b.example" in out
    assert "c https://c.example" not in out
    assert out.output_metadata["source"] == "web_search"


def test_web_search_empty_results_report_no_match():
    tool = WebSearchTool(searcher=lambda query, limit: [])
    out = _invoke(tool, query="nothing")
    assert "无匹配结果" in out


# -- todo --------------------------------------------------------------------


def test_todo_replaces_state_and_renders_marks():
    state = TodoState()
    tool = TodoTool(state=state)

    out = _invoke(
        tool,
        todos=[
            {"id": "t1", "content": "读代码", "status": "done"},
            {"id": "t2", "content": "写测试", "status": "in_progress"},
            {"id": "t3", "content": "提交", "status": "pending"},
        ],
    )

    assert "[x] t1: 读代码" in out
    assert "[~] t2: 写测试" in out
    assert "[ ] t3: 提交" in out
    assert [item.id for item in state.items()] == ["t1", "t2", "t3"]

    out = _invoke(tool, todos=[{"id": "t1", "content": "读代码", "status": "pending"}])
    assert "t2" not in out and "t3" not in out
    assert len(state.items()) == 1


def test_todo_empty_list_clears_state():
    tool = TodoTool()
    _invoke(tool, todos=[{"id": "t1", "content": "任务", "status": "pending"}])
    out = _invoke(tool, todos=[])
    assert "任务清单为空" in out


def test_todo_rejects_duplicate_ids():
    tool = TodoTool()
    with pytest.raises(ValueError, match="不唯一"):
        _invoke(
            tool,
            todos=[
                {"id": "t1", "content": "a", "status": "pending"},
                {"id": "t1", "content": "b", "status": "pending"},
            ],
        )


def test_todo_rejects_over_limit():
    tool = TodoTool()
    todos = [
        {"id": f"t{index}", "content": "x", "status": "pending"} for index in range(MAX_TODOS + 1)
    ]
    with pytest.raises(ValueError, match="超限"):
        _invoke(tool, todos=todos)


def test_todo_item_model_rejects_empty_fields():
    with pytest.raises(ValueError):
        TodoItem(id="", content="x", status="pending")
