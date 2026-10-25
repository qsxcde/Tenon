"""工具展示块 mixin 宿主的类型声明基类。

``ToolLifecycleMixin`` 组合进 ``ToolCallBlock`` 后通过 ``self`` 访问宿主属性；
mypy 无法从 mixin 推断宿主成员，故在此集中声明。本文件只含类级类型注解，
不包含默认值、赋值或方法体，运行时行为完全由宿主类提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..output import OutputBuffer


class ToolBlockHost:
    """ToolLifecycleMixin 的宿主属性与方法声明（仅类型，无行为）。"""

    status: str
    awaiting: bool
    rejected: bool
    result: str
    execution_status: str
    cleanup_status: str
    progress_text: str
    elapsed_ms: int | None
    queue_position: int | None
    error_code: str | None
    output_buffer: OutputBuffer | None
    _lifecycle_seen: bool
    _result_applied: bool
    touch: Callable[[], None]
