"""TUI 组合根装配：模型窗口写入、运行时重载与会话端口重建。

全部用桩替换 client/session 工厂，不启动真实 TUI 或模型，标记 unit。
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from tenon.ai.catalog.registry import ModelRegistry
from tenon.ai.catalog.store import ModelStore
from tenon.app import config as app_config
from tenon.app.composition.tui import config as tui_config
from tenon.app.composition.tui.factory import TuiAssembler

pytestmark = pytest.mark.unit


def _assembler(**kwargs: Any) -> TuiAssembler:
    return TuiAssembler(
        provider=kwargs.pop("provider", "deepseek"),
        model=kwargs.pop("model", "deepseek-v4-pro"),
        reasoning_effort=kwargs.pop("reasoning_effort", "high"),
        registry=kwargs.pop("registry", ModelRegistry(ModelStore(None))),
        **kwargs,
    )


def test_target_provider_resolves_unique_owner():
    """新模型只属于一个 provider 时自动推断,否则沿用显式值。"""
    assembler = _assembler()

    assert assembler._target_provider("deepseek-v4-pro", None) == "deepseek"
    assert assembler._target_provider(None, "glm") == "glm"
    assert assembler._target_provider(None, None) is None


def test_active_selection_returns_provider_and_model():
    """当前选择由 provider 与装配模型解析得出。"""
    assembler = _assembler()

    provider, model_id = assembler._active_selection()

    assert provider == "deepseek"
    assert model_id


def test_rebuild_config_without_manager_raises():
    """未完成 SessionManager 装配时重建配置立即报错,避免半装配状态生效。"""
    assembler = _assembler()

    with pytest.raises(RuntimeError, match="SessionManager"):
        assembler.rebuild_config()


async def test_rebuild_config_async_without_manager_raises():
    """异步重建同样要求已完成管理器装配。"""
    assembler = _assembler()

    with pytest.raises(RuntimeError, match="SessionManager"):
        await assembler.rebuild_config_async()


async def test_reload_runtime_async_rebuilds_with_current_selection(monkeypatch):
    """/mcp reload 走统一重建入口,不改变当前 provider/model/effort。"""
    assembler = _assembler()
    calls: list[tuple[Any, Any, Any]] = []

    async def fake_rebuild(provider=None, model=None, effort=None):
        calls.append((provider, model, effort))
        return ("m", "low")

    monkeypatch.setattr(assembler, "rebuild_config_async", fake_rebuild)

    assert await assembler.reload_runtime_async() == ("m", "low")
    assert calls == [(None, None, None)]


async def test_set_context_window_writes_override_and_hot_swaps(monkeypatch, tmp_path):
    """窗口写入 models.json(保留元数据)后重建注册表并返回新来源。"""
    models = tmp_path / "models.json"
    monkeypatch.setattr(app_config, "CONFIG_MODELS_FILE", models)
    assembler = _assembler()
    calls: list[tuple[Any, Any, Any]] = []

    async def fake_rebuild(provider=None, model=None, effort=None):
        calls.append((provider, model, effort))
        return ("deepseek-v4-pro", "high")

    monkeypatch.setattr(assembler, "rebuild_config_async", fake_rebuild)

    window, source = await assembler.set_context_window(131_072)

    assert (window, source) == (131_072, "catalog")
    assert calls == [("deepseek", "deepseek-v4-pro", "high")]
    record = json.loads(models.read_text(encoding="utf-8"))["deepseek"]["models"][0]
    assert record["id"] == "deepseek-v4-pro"
    assert record["contextWindow"] == 131_072
    assert record["reasoning"] is True  # 内置元数据被保留


async def test_set_context_window_rejects_non_positive():
    """非正整数窗口在写盘前被拒绝。"""
    assembler = _assembler()

    with pytest.raises(ValueError, match="正整数"):
        await assembler.set_context_window(0)


async def test_set_context_window_requires_provider(monkeypatch):
    """无法确定 provider 时明确报错,不写无效的 models.json 键。"""
    assembler = _assembler()
    monkeypatch.setattr(assembler, "_active_selection", lambda: (None, "m-1"))

    with pytest.raises(ValueError, match="provider"):
        await assembler.set_context_window(8_000)


def test_create_child_session_disables_recursive_subagents(monkeypatch):
    """子会话按 profile 限制工具、禁用嵌套委派且不进入普通 store。"""
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_create(cfg=None, **kwargs):
        captured["cfg"] = cfg
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(tui_config, "create_agent_session", fake_create)
    assembler = _assembler()

    result = assembler._create_child_session(SimpleNamespace(profile="explore"))

    assert result is sentinel
    assert captured["enable_subagents"] is False
    assert captured["store"] is None
    assert captured["allowed_tool_names"]
    assert captured["system_prompt_suffix"]


def test_build_summarizer_wraps_new_client(monkeypatch):
    """摘要器由组合根创建 client 后包装,不在模块加载期构造。"""
    client = object()
    captured: dict[str, Any] = {}

    class _Summarizer:
        def __init__(self, wrapped: Any) -> None:
            captured["client"] = wrapped

    monkeypatch.setattr(tui_config.model_selection, "create_llm", lambda **kwargs: client)
    monkeypatch.setattr(
        "tenon.app.composition.model.factory.LlmSummarizer",
        _Summarizer,
    )
    assembler = _assembler()

    assembler._build_summarizer()

    assert captured["client"] is client


def test_restore_session_config_prefers_unique_catalog_owner(monkeypatch):
    """恢复会话时按会话头模型推断 provider,并沿用会话记录的思考强度。"""
    captured: dict[str, Any] = {}
    sentinel = object()

    def fake_create_config(cfg=None, **kwargs):
        captured["cfg"] = cfg
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(tui_config, "create_agent_config", fake_create_config)
    assembler = _assembler(provider="glm")
    ref = SimpleNamespace(model="deepseek-v4-pro", effort="medium")

    result = assembler._restore_session_config(ref)

    assert result is sentinel
    assert captured["provider"] == "deepseek"
    assert captured["model"] == "deepseek-v4-pro"
    assert captured["reasoning_effort"] == "medium"


def test_refresh_skills_delegates_to_skills_view(monkeypatch):
    """技能视图每次刷新都重读注册表,不使用启动快照。"""
    from tenon.app.composition.tui import factory as tui_factory

    calls: list[Any] = []

    def fake_view(cfg):
        calls.append(cfg)
        return ([], ["diag"])

    monkeypatch.setattr(tui_factory, "skills_view", fake_view)
    assembler = _assembler()

    assert assembler.refresh_skills() == ([], ["diag"])
    assert calls == [None]
