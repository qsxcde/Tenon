"""连续工具调用的分组摘要块。

分组头只在出现第二个连续工具调用时才创建; 折叠时子工具块不渲染,
展开后仍复用各自的点击折叠与详情展示。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..primitives import Component, RichLine, _cell_width, _seg, _truncate
from ..theme import DIM, ERROR, SUCCESS, TEXT, WARNING

if TYPE_CHECKING:
    from .tool_blocks import ToolCallBlock

__all__ = ["ToolGroupBlock"]


class ToolGroupBlock(Component):
    """同一轮连续工具调用的折叠摘要头。"""

    def __init__(self) -> None:
        super().__init__()
        self.members: list[ToolCallBlock] = []
        self.expanded = False

    def add(self, block: ToolCallBlock) -> None:
        """把工具块纳入分组，成员变化时同步刷新分组摘要。"""
        self.members.append(block)
        block.group = self
        block.group_collapsed = not self.expanded
        block.add_touch_listener(self._on_member_touched)
        for member in self.members:
            member.touch()
        self.touch()

    def _on_member_touched(self, _block: Component) -> None:
        self.touch()

    def toggle_expand(self) -> None:
        """展开/折叠整组工具调用，并让子块的隐藏状态同步失效。"""
        self.expanded = not self.expanded
        for member in self.members:
            member.group_collapsed = not self.expanded
            member.touch()
        self.touch()

    def render(self, width: int) -> list[RichLine]:
        icon, icon_tag = self._aggregate_status()
        header: RichLine = [
            _seg("▼" if self.expanded else "▶", fg=DIM),
            _seg(" "),
            _seg(icon, fg=icon_tag),
            _seg(" "),
            _seg(f"{len(self.members)} 个工具调用", fg=TEXT),
        ]
        names = "" if self.expanded else self._names()
        if names:
            remaining = width - sum(_cell_width(span.text) for span in header)
            if remaining > 4:
                header.append(_seg(_truncate(f" · {names}", remaining), fg=DIM))
        return [header]

    def _aggregate_status(self) -> tuple[str, str]:
        if any(member.status == "error" for member in self.members):
            return "✗", ERROR
        if any(member.status == "pending" for member in self.members):
            return "·", WARNING
        return "✓", SUCCESS

    def _names(self) -> str:
        counts: dict[str, int] = {}
        for member in self.members:
            counts[member.name] = counts.get(member.name, 0) + 1
        return " · ".join(f"{name} ×{count}" for name, count in counts.items())
