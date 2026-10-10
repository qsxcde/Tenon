"""TUI 渲染层组件。

组件依赖 primitives、blocks 和 status 等表现层对象，不依赖具体 Textual 实现。
"""

from .blocks import (
    ActivityBlock,
    AssistantBlock,
    CancelledBlock,
    ErrorBlock,
    ToolCallBlock,
    UserBlock,
)
from ..state.model import TuiModel
from .primitives import (
    Component,
    RichLine,
    Span,
)
from ..state.runtime import RuntimePhase, RuntimeReducer, RuntimeSnapshot
from .status import FooterInfo, StatusBar
from ..state.transcript import Transcript

__all__ = [
    "Span",
    "RichLine",
    "Component",
    "UserBlock",
    "AssistantBlock",
    "ActivityBlock",
    "ToolCallBlock",
    "ErrorBlock",
    "CancelledBlock",
    "Transcript",
    "StatusBar",
    "FooterInfo",
    "TuiModel",
    "RuntimePhase",
    "RuntimeSnapshot",
    "RuntimeReducer",
]
