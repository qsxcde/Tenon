"""TuiModel mixin 宿主的类型声明基类。

``state/model_*`` 下的 mixin 组合进 ``TuiModel`` 后通过 ``self`` 访问宿主
属性与方法;mypy 无法从 mixin 推断宿主成员,故在此集中声明。本文件只含
类级类型注解,不包含默认值、赋值或方法体:
- 属性只有类级注解;
- 方法以 ``Callable`` 属性注解声明,避免与宿主/其他 mixin 中真实 ``def``
  的签名差异产生 override 误报。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections import OrderedDict
    from collections.abc import Callable

    from ..presentation.blocks import AssistantBlock, SubagentBlock, ToolCallBlock
    from ..presentation.status import StatusBar
    from .runtime import RuntimeReducer, RuntimeSnapshot
    from .transcript import Transcript
    from tenon.core.context.diagnostics import ContextDiagnostics


class TuiModelHost:
    """TuiModel 组合宿主的属性声明（ModelHistoryMixin / ModelEventMixin 等共享）。"""

    # -- 宿主 __init__ 建立的投影状态 -------------------------------------
    transcript: Transcript
    status: StatusBar
    running: bool
    _clock: Callable[[], float]
    _assistant: AssistantBlock | None
    _pending_tools: list[ToolCallBlock]
    _pending_tools_by_id: dict[str, ToolCallBlock]
    _tool_blocks_by_id: dict[str, ToolCallBlock]
    _result_event_ids: set[str]
    _subagent_blocks_by_id: OrderedDict[str, SubagentBlock]
    _subagent_evicted_ids: set[str]
    _pending_user_prompts: list[str]
    activity_visible: bool
    activity_frame: int
    runtime: RuntimeSnapshot
    context_diagnostics: ContextDiagnostics
    _runtime_reducer: RuntimeReducer
    render_stats: dict[str, int | float]
    output_stats: dict[str, int]
    _event_count: int

    # -- 宿主方法(mixin 调用) ---------------------------------------------
    _ensure_assistant: Callable[[], AssistantBlock]
    append_info: Callable[[str], None]
