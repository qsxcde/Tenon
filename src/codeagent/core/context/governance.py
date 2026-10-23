"""Request-scoped governance of tool results.

Given one request budget snapshot, tool messages are detached, trimmed to the
space actually left after system prompt, tool definitions and conversation,
and re-labelled with structured facts. The operation is deterministic and
never mutates session history.
"""

from __future__ import annotations

import copy

from codeagent.core.context.budget import _estimate_message_tokens
from codeagent.core.contracts.messages import (
    Message,
    OutputCompleteness,
    ToolCall,
    ToolOutputMetadata,
)

__all__ = ["govern_tool_messages", "clone_message"]

#: 请求预算裁剪后附加在正文末尾的说明。
CROP_SUFFIX = "\n[工具结果已按请求预算裁剪]"
#: 连说明都放不下时的占位。
OMITTED = "[工具结果已省略]"


def govern_tool_messages(messages: list[Message], budget) -> list[Message]:
    """Return a detached message view whose tool results fit this request.

    The operation is deterministic and request-local.  It never mutates the
    session history, and keeps structured facts in a tool message even when
    its visible body must be reduced to a metadata-only summary.
    """
    tools = [message for message in messages if message.role == "tool"]
    if not tools:
        return [clone_message(message) for message in messages]
    non_tool_tokens = budget.input_tokens - budget.tool_result_tokens
    available_tokens = max(0, budget.input_budget - non_tool_tokens)
    remaining = available_tokens
    remaining_tools = len(tools)
    replacements: dict[str, Message] = {}
    for message in tools:
        current_tokens = _estimate_message_tokens(message)
        allocation = max(1, remaining // remaining_tools) if remaining else 0
        if current_tokens <= allocation:
            replacement = clone_message(message)
        else:
            replacement = _crop_tool_message(message, allocation)
        replacements[message.id] = replacement
        remaining = max(0, remaining - _estimate_message_tokens(replacement))
        remaining_tools -= 1
    return [replacements.get(message.id, clone_message(message)) for message in messages]


def _crop_tool_message(message: Message, allocation: int) -> Message:
    metadata = message.tool_output or ToolOutputMetadata(
        completeness=OutputCompleteness.UNKNOWN,
        total_bytes=len(message.content.encode("utf-8")),
        total_lines=len(message.content.splitlines()),
        shown_bytes=len(message.content.encode("utf-8")),
        shown_lines=len(message.content.splitlines()),
        source="legacy",
    )
    summary = _tool_metadata_summary(metadata)
    content = _fit_cropped_content(summary, message.content, allocation)
    cropped = ToolOutputMetadata(
        completeness=OutputCompleteness.TRUNCATED,
        total_bytes=metadata.total_bytes,
        total_lines=metadata.total_lines,
        shown_bytes=len(content.encode("utf-8")),
        shown_lines=len(content.splitlines()),
        truncated_by="request_budget",
        path=metadata.path,
        range_start=metadata.range_start,
        range_end=metadata.range_end,
        exit_code=metadata.exit_code,
        duration_ms=metadata.duration_ms,
        stderr_summary=metadata.stderr_summary,
        change_summary=metadata.change_summary,
        artifact_path=metadata.artifact_path,
        artifact_ref=metadata.artifact_ref,
        continuation=metadata.continuation,
        semantic_success=metadata.semantic_success,
        source="budget",
        unsupported_blocks=metadata.unsupported_blocks,
    )
    return clone_message(message, content=content, tool_output=cropped)


def _fit_cropped_content(summary: str, body: str, allocation: int) -> str:
    """Trim a tool body until the *estimated tokens* fit the allocation.

    A character budget derived by multiplying tokens by four only holds for
    ASCII; CJK metadata and bodies need far fewer characters per token, so the
    crop is validated against the same estimator the budget uses.
    """
    if allocation <= 0:
        return OMITTED
    if _estimate_message_tokens(Message(role="tool", content=CROP_SUFFIX)) > allocation:
        return OMITTED
    low, high = 0, len(body)
    best = f"{summary}{CROP_SUFFIX}"
    while low <= high:
        middle = (low + high) // 2
        candidate = f"{summary}\n{body[:middle]}{CROP_SUFFIX}"
        if _estimate_message_tokens(Message(role="tool", content=candidate)) <= allocation:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def _tool_metadata_summary(metadata: ToolOutputMetadata) -> str:
    fields = [f"完整性={metadata.completeness}"]
    if metadata.path:
        fields.append(f"路径={metadata.path}")
    if metadata.exit_code is not None:
        fields.append(f"退出码={metadata.exit_code}")
    if metadata.total_bytes is not None:
        fields.append(f"总字节={metadata.total_bytes}")
    if metadata.total_lines is not None:
        fields.append(f"总行数={metadata.total_lines}")
    if metadata.truncated_by:
        fields.append(f"原因={metadata.truncated_by}")
    if metadata.change_summary:
        fields.append(f"变更={metadata.change_summary}")
    return "[工具结果元数据] " + ", ".join(fields)


def clone_message(
    message: Message,
    *,
    content: str | None = None,
    tool_output: ToolOutputMetadata | None = None,
) -> Message:
    """Return a detached copy, optionally replacing content or output facts."""
    return Message(
        role=message.role,
        content=message.content if content is None else content,
        tool_calls=[
            ToolCall(
                id=call.id,
                name=call.name,
                args=copy.deepcopy(call.args),
                details=copy.deepcopy(call.details),
            )
            for call in message.tool_calls
        ],
        tool_call_id=message.tool_call_id,
        id=message.id,
        parent_id=message.parent_id,
        tool_output=message.tool_output if tool_output is None else tool_output,
    )
