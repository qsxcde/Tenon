"""TUI 维护类命令：快照恢复、会话导出、委派管理与上下文窗口。

这些命令都依赖组合根注入的 ``TuiAdminPort``(快照存储、运行时重载、委派槽位、
模型目录写入),视图层只做参数校验与结果呈现。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from codeagent.app.errors.reporting import report_unexpected_error
from ..ports.admin import TuiAdminPort
from .host import TuiAppHost
from .parser import Command

_UNDO_LIST_LIMIT = 20


class TuiAdminCommandCoordinator(TuiAppHost):
    # -- /undo ------------------------------------------------------------
    def _cmd_undo(self, cmd: Command) -> None:
        """查看或恢复写前快照(``/undo`` 恢复最近一次,``list``/``preview`` 只读)。"""
        admin = self._admin
        if admin is None:
            self.model.append_info("当前环境不支持快照操作(未注入维护端口)")
            return
        action = cmd.args[0] if cmd.args else "restore"
        try:
            if action == "list":
                self.model.append_info(self._format_checkpoints(admin))
            elif action in {"preview", "show"}:
                self._preview_checkpoint(admin)
            elif action in {"restore", "last"}:
                self._restore_checkpoint(admin)
            else:
                self.model.append_info("用法: /undo [list|preview]")
        except (OSError, ValueError) as exc:
            self.model.append_info(f"快照操作失败:{exc}")
        self._schedule_render()

    def _format_checkpoints(self, admin: TuiAdminPort) -> str:
        entries = admin.list_checkpoints(limit=_UNDO_LIST_LIMIT)
        if not entries:
            return "写前快照: (无)"
        lines = [f"写前快照 ({len(entries)},新到旧):"]
        lines.extend(
            f"  seq={entry.seq} {entry.created_at} "
            f"{'改写' if entry.existed else '新建'} {entry.path}"
            for entry in entries
        )
        lines.append("提示: /undo preview 查看将恢复项 · /undo 恢复最近一次")
        return "\n".join(lines)

    def _preview_checkpoint(self, admin: TuiAdminPort) -> None:
        entries = admin.list_checkpoints(limit=1)
        if not entries:
            self.model.append_info("写前快照: (无)")
            return
        entry = entries[0]
        suffix = "" if entry.existed else " · 文件原本不存在,恢复时会删除"
        self.model.append_info(f"将恢复: {entry.path} (seq={entry.seq}){suffix}")

    def _restore_checkpoint(self, admin: TuiAdminPort) -> None:
        entry = admin.restore_checkpoint()
        suffix = "" if entry.existed else " · 文件原本不存在,已删除"
        self.model.append_info(f"已恢复: {entry.path} (seq={entry.seq}){suffix}")

    # -- /export ----------------------------------------------------------
    def _cmd_export(self, cmd: Command) -> None:
        """把当前会话的完整文档导出到指定路径。"""
        if not cmd.args:
            self.model.append_info("用法: /export <path>")
            return
        path = Path(cmd.args[0]).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            lines = list(self.model.transcript.iter_lines(self._transcript_width()))
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError as exc:
            self.model.append_info(f"导出失败:{exc}")
            self._schedule_render()
            return
        self.model.append_info(f"已导出 {len(lines)} 行会话文档到 {path}")
        self._schedule_render()

    # -- /subagents -------------------------------------------------------
    def _cmd_subagents(self, cmd: Command) -> None:
        """列出委派槽位状态,或取消指定委托。"""
        admin = self._admin
        if admin is None:
            self.model.append_info("当前环境不支持委派管理(未注入维护端口)")
            return
        action = cmd.args[0] if cmd.args else "list"
        if action == "cancel":
            if len(cmd.args) < 2:
                self.model.append_info("用法: /subagents cancel <delegation-id>")
            else:
                self._cancel_subagent(admin, cmd.args[1])
            self._schedule_render()
            return
        if action not in {"list", "status"}:
            self.model.append_info("用法: /subagents [list|cancel <delegation-id>]")
            self._schedule_render()
            return
        try:
            snapshot = admin.subagent_snapshot()
        except (AttributeError, ValueError) as exc:
            self.model.append_info(f"读取委派状态失败:{exc}")
            self._schedule_render()
            return
        self.model.append_info(self._format_subagents(snapshot))
        self._schedule_render()

    def _format_subagents(self, snapshot: dict[str, Any]) -> str:
        active = dict(snapshot.get("active") or {})
        lines = [
            f"并发上限: {snapshot.get('max_concurrency')} "
            f"(配置 {snapshot.get('configured_max_concurrency')})",
            f"活跃委派: {len(active)}",
        ]
        lines.extend(
            f"  {delegation_id} → {session_id or '(子会话未就绪)'}"
            for delegation_id, session_id in sorted(active.items())
        )
        if not active:
            lines.append("  (无)")
        lines.append(f"已观测委派块: {len(self.model.subagent_blocks)}")
        lines.append("提示: /subagents cancel <delegation-id> 终止单个委派")
        return "\n".join(lines)

    def _cancel_subagent(self, admin: TuiAdminPort, delegation_id: str) -> None:
        async def run() -> None:
            try:
                cancelled = await admin.cancel_subagent(delegation_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 委派失败需完整诊断
                self.model.append_info(report_unexpected_error("取消委派", exc))
            else:
                if cancelled:
                    self.model.append_info(f"已取消委派: {delegation_id}")
                else:
                    self.model.append_info(f"未找到活跃委派: {delegation_id}")
            self._schedule_render()

        self._track_task(asyncio.get_running_loop().create_task(run()))

    # -- /mcp reload ------------------------------------------------------
    def _reload_mcp(self) -> None:
        """重建模型、MCP 与工具运行时(改完 MCP 配置后免重启生效)。"""
        admin = self._admin
        if admin is None:
            self.model.append_info("当前环境不支持重载 MCP(未注入维护端口)")
            self._schedule_render()
            return

        async def run() -> None:
            try:
                model, effort = await admin.reload_runtime()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - 重载失败需完整诊断
                self.model.append_info(report_unexpected_error("重载运行时", exc))
            else:
                self.model.status.model, self.model.status.effort = model, effort
                self.model.append_info("已重载 MCP 与工具运行时")
                self._refresh_model_capabilities(self._provider, model, effort)
            self._schedule_render()

        self.model.append_info("正在重载 MCP 与工具运行时...")
        self._schedule_render()
        self._track_task(asyncio.get_running_loop().create_task(run()))

    # -- /context-window --------------------------------------------------
    def _cmd_context_window(self, cmd: Command) -> None:
        """显示或设置当前模型的上下文窗口(写入 models.json 并热切换)。"""
        admin = self._admin
        if admin is None:
            self.model.append_info("当前环境不支持修改上下文窗口(未注入维护端口)")
            return
        if not cmd.args:
            self.model.append_info(self._context_window_text())
            self._schedule_render()
            return
        try:
            tokens = _parse_tokens(cmd.args[0])
        except ValueError as exc:
            self.model.append_info(str(exc))
            self._schedule_render()
            return
        self._apply_context_window(admin, tokens)

    def _context_window_text(self) -> str:
        capabilities = self.model.status.model_capabilities
        window = getattr(capabilities, "context_window", None)
        source = getattr(capabilities, "window_source", None) or "unknown"
        if not isinstance(window, int):
            return "上下文窗口: 未知 · 用法: /context-window <tokens>"
        return (
            f"上下文窗口: {window:,} · 来源 {source}\n"
            "用法: /context-window <tokens>(支持 131072 / 128k / 131,072)"
        )

    def _apply_context_window(self, admin: TuiAdminPort, tokens: int) -> None:
        async def run() -> None:
            try:
                window, source = await admin.set_context_window(tokens)
            except asyncio.CancelledError:
                raise
            except (OSError, ValueError) as exc:
                self.model.append_info(f"设置上下文窗口失败:{exc}")
            except Exception as exc:  # noqa: BLE001 - 重载失败需完整诊断
                self.model.append_info(report_unexpected_error("设置上下文窗口", exc))
            else:
                self.model.append_info(f"已设置上下文窗口: {window:,} · 来源 {source}")
                self._refresh_model_capabilities(
                    self._provider, self.model.status.model, self.model.status.effort
                )
            self._schedule_render()

        self.model.append_info(f"正在写入上下文窗口 {tokens} 并热切换...")
        self._schedule_render()
        self._track_task(asyncio.get_running_loop().create_task(run()))


def _parse_tokens(raw: str) -> int:
    """解析 ``131072`` / ``128k`` / ``131,072`` 形式的窗口值。"""
    text = raw.strip().replace(",", "").replace("_", "")
    multiplier = 1
    if text.lower().endswith("k"):
        multiplier, text = 1024, text[:-1]
    elif text.lower().endswith("m"):
        multiplier, text = 1024 * 1024, text[:-1]
    if not text.isdigit():
        raise ValueError(f"上下文窗口必须是正整数: {raw}(支持 131072 / 128k)")
    tokens = int(text) * multiplier
    if tokens < 1:
        raise ValueError("上下文窗口必须大于 0")
    return tokens
