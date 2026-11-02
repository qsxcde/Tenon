"""TUI 上下文窗口写入:上限校验 + models.json 覆盖 + 注册表刷新。

窗口写入必须整条链路复用,否则 ``/context-window`` 与 ``/model <id>:1m`` 会各自
维护一份校验规则,出现一条入口能绕过上限的情况。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..model.window import ensure_window_within_limit
from .admin import model_override_record

__all__ = ["write_context_window"]


def write_context_window(
    registry: Any,
    provider: str,
    model_id: str,
    tokens: int,
    path: Path,
) -> Any:
    """校验上限后写入一条覆盖记录,返回重新加载的注册表。

    上限校验针对模型的 ``max_context_window``(缺省用 ``context_window``);模型
    没有声明上限时保持旧行为,不猜测。
    """
    if type(tokens) is not int or tokens < 1:
        raise ValueError("上下文窗口必须为正整数")
    from tenon.ai.catalog.registry import ModelRegistry
    from tenon.ai.catalog.store import ModelStore

    spec = registry.resolve(model_id, provider=provider)
    ensure_window_within_limit(tokens, spec)
    store = ModelStore(path)
    store.write_model_override(provider, model_override_record(spec, tokens))
    # ModelStore 不做缓存,load() 每次重读文件,复用实例即可拿到刚写入的覆盖。
    return ModelRegistry(store)
