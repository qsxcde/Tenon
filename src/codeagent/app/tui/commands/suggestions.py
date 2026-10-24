"""TUI 补全浮层的渲染与值标记。

从交互协调器拆出,避免单文件持续膨胀;本模块只决定"怎么画候选",候选计算与
键位分派仍在 ``interaction.py``。
"""

from __future__ import annotations

from ..presentation.theme import ACCENT, DIM, SUCCESS
from ..presentation.primitives import Span
from .host import TuiAppHost
from .registry import _COMMANDS

#: 候选总数上限与浮层固定视口行数(窗口切片只影响渲染,索引仍指向全量候选)。
_MAX_SUGGESTIONS = 64
_SUGGESTION_WINDOW = 9


class TuiSuggestionRenderMixin(TuiAppHost):
    def _render_suggestions(self) -> None:
        if not self._suggestions:
            self._backend.set_suggestions([])
            return
        total = len(self._suggestions)
        window = min(_SUGGESTION_WINDOW, total)
        start = min(max(0, self._suggestion_index - window // 2), max(0, total - window))
        lines: list[list[Span]] = []
        for index in range(start, start + window):
            name = self._suggestions[index]
            active = index == self._suggestion_index
            fg = ACCENT if active else DIM
            spans = [Span("› " if active else "  ", fg=fg)]
            if self._suggestion_kind == "command":
                spans.append(Span(f"/{name}", fg=fg))
                spans.append(Span(f" — {_COMMANDS[name].summary}", fg=DIM))
            else:
                marked = self._value_marked(name) if self._suggestion_kind == "value" else False
                spans.append(Span("✓ " if marked else "  ", fg=SUCCESS if marked else DIM))
                spans.append(Span(self._value_label(name), fg=fg))
            lines.append(spans)
        self._backend.set_suggestions(lines)

    def _value_marked(self, name: str) -> bool:
        """值候选的 ✓ 标记:model/effort/provider 标记当前生效项;login 标记已配置
        key 的 provider(组合根注入的 ``configured_providers``);sessions 标记当前会话。"""
        cmd_name = self._last_text[1:].partition(" ")[0]
        if cmd_name == "login":
            return name in self._configured_providers
        if cmd_name == "sessions":
            current = self._manager.current
            return current is not None and name == current.session_id
        return bool(self._current_picker_value()) and name == self._current_picker_value()

    def _value_label(self, name: str) -> str:
        """值候选的展示串:sessions 显示标题(+ id 前 8 位,可区分),其余原样。"""
        cmd_name = self._last_text[1:].partition(" ")[0]
        if cmd_name != "sessions":
            return name
        for ref in self._manager.list():
            if ref.id == name:
                title = ref.title or "(无标题)"
                return f"{title} ({name[:8]}…)"
        return name
