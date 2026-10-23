"""Execute one model-requested AgentTool and apply runtime hooks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from codeagent.core.support.awaiting import await_if_needed
from codeagent.core.context.model import AgentContext
from codeagent.core.contracts.errors import AgentRuntimeError
from codeagent.core.contracts.events import (
    SUBAGENT_EVENT_TYPES,
    AgentEvent,
    EventType,
)
from codeagent.core.contracts.messages import ToolCall, ToolExecutionStatus, ToolResult
from codeagent.core.contracts.ports import AgentTool
from codeagent.core.orchestration.config import AgentLoopConfig
from codeagent.core.orchestration.tool_hooks import run_post_chain, run_pre_chain


#: 安全警告前缀:单行、固定格式,便于订阅方按行剥离。
_WARNING_PREFIX = "[安全提示] "
NEWLINE = chr(10)


async def new_tool_result(
    tool: AgentTool | None,
    call: ToolCall,
    context: AgentContext,
    config: AgentLoopConfig,
    emit: Callable[[AgentEvent], Any],
    operation_id: str | None = None,
) -> ToolResult:
    """Run one strictly adapted AgentTool and normalize its result."""
    if call.details.get("argument_error"):
        return ToolResult(
            call.id,
            f"[工具参数错误] {call.details['argument_error']}",
            error=True,
            name=call.name,
            status=ToolExecutionStatus.INVALID_ARGUMENTS,
            operation_id=operation_id or "",
            cleanup_confirmed=True,
        )
    if tool is None:
        return _unknown_tool_result(call, operation_id)
    pre = await run_pre_chain(config.before_tool_calls, call, context)
    if pre.blocked_reason is not None:
        return _rejected_result(tool, call, pre.blocked_reason, operation_id)
    call = pre.call
    try:
        result = await _execute_tool(tool, call, config, emit, operation_id)
    except Exception as exc:  # noqa: BLE001 - tool errors are model-visible
        result = ToolResult(
            call.id,
            f"[工具执行出错] {exc}",
            error=True,
            name=call.name,
            status=ToolExecutionStatus.FAILED,
            operation_id=operation_id or "",
            cleanup_confirmed=True,
        )
    result = await run_post_chain(config.after_tool_calls, call, result, context)
    if pre.warnings:
        # 多条警告合并进单一安全提示行,保持前缀可按行剥离。
        result = _with_warning(result, "; ".join(pre.warnings))
    if not result.operation_id:
        result.operation_id = operation_id or ""
    return result


def _with_warning(result: ToolResult, warning: str) -> ToolResult:
    """Prefix an allowed-but-noteworthy call so the model can see it.

    The text stays on one line and the structured metadata is untouched, so
    downstream consumers keep parsing the same facts.
    """
    if not warning or result.content.startswith(_WARNING_PREFIX):
        return result
    result.content = f"{_WARNING_PREFIX}{warning}{NEWLINE}{result.content}"
    return result


def _rejected_result(
    tool: AgentTool,
    call: ToolCall,
    reason: str,
    operation_id: str | None,
) -> ToolResult:
    """门禁短路的模型可见拒绝结果(不执行工具、不跑 post 链)。"""
    return ToolResult(
        call.id,
        f"[工具执行被拒绝] {reason}",
        error=True,
        name=tool.name,
        rejected=True,
        status=ToolExecutionStatus.REJECTED,
        operation_id=operation_id or "",
        cleanup_confirmed=True,
    )


async def _execute_tool(
    tool: AgentTool,
    call: ToolCall,
    config: AgentLoopConfig,
    emit: Callable[[AgentEvent], Any],
    operation_id: str | None,
) -> ToolResult:
    runtime = config.tool_runtime
    if runtime is None:
        raise AgentRuntimeError("工具运行时未配置")

    async def on_update(update: Any) -> None:
        if isinstance(update, AgentEvent) and update.type in SUBAGENT_EVENT_TYPES:
            emit(update)
            return
        elapsed_ms = 0
        if isinstance(update, dict) and update.get("elapsed_ms") is not None:
            try:
                elapsed_ms = max(0, int(update["elapsed_ms"]))
            except (TypeError, ValueError):
                elapsed_ms = 0
        emit(
            AgentEvent(
                EventType.TOOL_EXECUTION_UPDATE,
                payload=update,
                metadata={
                    "tool_call_id": call.id,
                    "tool_name": call.name,
                    "operation_id": operation_id,
                    "status": "running",
                    "elapsed_ms": elapsed_ms,
                },
                tool_call_id=call.id,
                operation_id=operation_id,
                status="running",
                tool_name=call.name,
                elapsed_ms=elapsed_ms,
            )
        )

    def on_start(operation: Any) -> None:
        actual_operation_id = str(getattr(operation, "operation_id", operation_id or ""))
        metadata = {
            "tool_call_id": call.id,
            "tool_name": call.name,
            "operation_id": actual_operation_id,
            "status": "running",
            "elapsed_ms": 0,
        }
        emit(
            AgentEvent(
                EventType.TOOL_EXECUTION_START,
                payload={"tool_call_id": call.id, "tool_name": call.name, "args": call.args},
                metadata=metadata,
                tool_call_id=call.id,
                operation_id=actual_operation_id,
                status="running",
                tool_name=call.name,
                elapsed_ms=0,
            )
        )

    return await runtime.execute(
        tool,
        call,
        timeout=config.tool_timeout,
        operation_id=operation_id,
        on_update=on_update,
        on_start=on_start,
    )


def _unknown_tool_result(call: ToolCall, operation_id: str | None) -> ToolResult:
    return ToolResult(
        call.id,
        f"[工具执行出错] 未知工具: {call.name}",
        error=True,
        name=call.name,
        status=ToolExecutionStatus.FAILED,
        operation_id=operation_id or "",
        cleanup_confirmed=True,
    )


__all__ = ["new_tool_result"]
