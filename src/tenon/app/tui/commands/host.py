"""TUI 协调器 mixin 宿主的类型声明基类。

``commands/*`` 与 ``session/*`` 下的 mixin 组合进 ``TuiApp`` 后通过 ``self``
访问宿主属性与方法;mypy 无法从 mixin 推断宿主成员,故在此集中声明。
本文件只含类级类型注解,不包含默认值、赋值或方法体,运行时行为完全由
``TuiApp`` 提供。跨 mixin 调用的方法以 ``Callable`` 属性声明,避免精确
签名与各实现不一致时产生 override 误报。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Callable
    from typing import Any

    from tenon.app.skills.models import Skill
    from tenon.app.tasks.modes import TaskMode
    from tenon.app.tasks.supervisor import TaskSupervisor

    from ..ports.admin import TuiAdminPort
    from ..ports.backend import TuiBackend
    from ..rendering.coordinator import TuiEventBuffer, TuiRenderCoordinator
    from ..state.model import TuiModel


class TuiAppHost:
    """TuiApp 各协调器 mixin 的宿主属性与方法声明(仅类型,无行为)。"""

    # -- 宿主状态 ---------------------------------------------------------
    model: TuiModel
    _manager: Any
    _backend: TuiBackend
    _event_buffer: TuiEventBuffer
    _render_coordinator: TuiRenderCoordinator
    # -- 组合根注入的装配数据与适配器 -------------------------------------
    _rebuild_ports: Any
    _rebuild_ports_async: Any
    _candidates: dict[str, Any]
    _agents_sources: list[str]
    _skills: list[Skill]
    _skill_diagnostics: list[str]
    _skills_by_name: dict[str, Skill]
    _mcp_diagnostics: list[str]
    _save_key: Any
    _configured_providers: set[str]
    _refresh_skills_callback: Callable[[], tuple[list[Skill], list[str]]] | None
    _package_action: Callable[[str, tuple[str, ...]], str] | None
    _close_runtime: Callable[[], Any] | None
    _resolve_model_capabilities: Callable[[str | None, str | None, str | None], Any] | None
    _admin: TuiAdminPort | None
    # -- 任务与登录状态 ---------------------------------------------------
    _task_mode: TaskMode
    _task_active: bool
    _task_supervisor: TaskSupervisor | None
    _login_pending: str | None
    # -- 输入建议与确认交互 -----------------------------------------------
    _suggestions: list[str]
    _suggestion_index: int
    _suggestion_kind: str
    _suppress_next_suggestions: bool
    _last_text: str
    _provider: str
    _pending_confirmation: dict[str, Any] | None
    # -- 异步任务与退出生命周期 -------------------------------------------
    _restore_task: asyncio.Task[None] | None
    _conversation_task: asyncio.Task[None] | None
    _session_action_task: asyncio.Task[None] | None
    _package_task: asyncio.Task[None] | None
    _shutdown_task: asyncio.Task[None] | None
    _background_tasks: set[asyncio.Task[Any]]
    _unsubscribe: Callable[[], None] | None
    _shutdown_started: bool
    _shutdown_complete: bool
    _accepting_input: bool
    # -- 跨 mixin 调用的宿主/协调器方法 ------------------------------------
    _schedule_render: Callable[[], None]
    _flush_render: Callable[[], None]
    _flush_render_now: Callable[[], None]
    _transcript_width: Callable[[], int]
    _track_task: Callable[[asyncio.Task[Any]], asyncio.Task[Any]]
    _exit: Callable[[], None]
    _schedule_session_action: Callable[..., bool]
    _hydrate_current_session: Callable[[], None]
    _refresh_skills: Callable[[], None]
    _run_conversation: Callable[..., None]
    _open_inline_picker: Callable[[str], None]
    _picker_candidates: Callable[[str], list[str]]
    _current_picker_value: Callable[[], str]
    _begin_login: Callable[[str], None]
    _end_login: Callable[[], None]
    _apply_config: Callable[..., bool]
    _refresh_model_capabilities: Callable[[str | None, str, str], None]
    # -- 斜杠命令处理器(dispatch 按名分派;签名各异,统一放宽) -------------
    _cmd_help: Callable[..., None]
    _cmd_ask: Callable[..., None]
    _cmd_plan: Callable[..., None]
    _cmd_code: Callable[..., None]
    _cmd_mode: Callable[..., None]
    _cmd_clear: Callable[..., None]
    _cmd_status: Callable[..., None]
    _cmd_name: Callable[..., None]
    _cmd_context: Callable[..., None]
    _cmd_tools: Callable[..., None]
    _cmd_sessions: Callable[..., None]
    _cmd_tree: Callable[..., None]
    _cmd_fork: Callable[..., None]
    _cmd_compact: Callable[..., None]
    _cmd_output: Callable[..., None]
    _cmd_retry: Callable[..., None]
    _cmd_continue: Callable[..., None]
    _cmd_skills: Callable[..., None]
    _cmd_mcp: Callable[..., None]
    _cmd_provider: Callable[..., None]
    _cmd_login: Callable[..., None]
    _cmd_model: Callable[..., None]
    _cmd_effort: Callable[..., None]
    _cmd_quit: Callable[..., None]
    _cmd_undo: Callable[..., None]
    _cmd_export: Callable[..., None]
    _cmd_subagents: Callable[..., None]
    _cmd_context_window: Callable[..., None]
    _reload_mcp: Callable[[], None]
