"""TUI 组合根 mixin 宿主的类型声明基类。

``TuiConfigMixin`` 组合进 ``TuiAssembler`` 后通过 ``self`` 访问宿主属性;
mypy 无法从 mixin 推断宿主成员,故在此集中声明。本文件只含类级类型注解,
不包含默认值、赋值或方法体,运行时行为完全由 ``TuiAssembler`` 提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from tenon.core.context.preflight import ContextPreflightConfig
    from tenon.tools.shared import ToolResourceLimits

    from ..runtime.extensions import RuntimeExtensions


class TuiAssemblerHost:
    """TuiConfigMixin 的宿主属性与方法声明(仅类型,无行为)。"""

    cfg: Any
    registry: Any
    store: Any
    reasoning_effort: str | None
    provider: str | None
    model: str | None
    uncertain_budget_policy: str
    context_preflight: ContextPreflightConfig | None
    extensions: RuntimeExtensions | None
    resource_limits: ToolResourceLimits | None
    mcp_diagnostics: list[str]
    refresh_skills: Callable[[], tuple[list[Any], list[str]]]
