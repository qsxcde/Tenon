"""MCP 结果内容投影与工具元数据。

把 SDK content block 到文本/诊断的映射与 server 客户端的线程-事件循环生命周期
分属两种职责:这里只负责"内容如何被解释",客户端负责"会话如何被驱动"。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mcp.types import TextContent

__all__ = ["McpCallResult", "McpToolInfo", "extract_result", "extract_text"]


@dataclass(frozen=True)
class McpCallResult:
    """Text projection plus explicit facts for non-text MCP content."""

    text: str
    metadata: dict[str, Any]


class McpToolInfo:
    """SDK ``tools/list`` 返回的工具元数据(适配器构造 McpTool 用)。"""

    def __init__(self, name: str, description: str | None, input_schema: dict[str, Any]) -> None:
        self.name = name
        self.description = description or ""
        self.input_schema = input_schema or {}


def _classify_block(block: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Split one content block into readable text or an unsupported descriptor."""
    if isinstance(block, TextContent):
        return block.text, None
    text = getattr(block, "text", None)
    if isinstance(text, str):
        return text, None
    block_type = str(getattr(block, "type", type(block).__name__))
    reference = getattr(block, "uri", None) or getattr(block, "url", None)
    return None, {
        "type": block_type,
        "reference": str(reference) if reference else None,
        "mime_type": getattr(block, "mimeType", None) or getattr(block, "mime_type", None),
    }


def _render_unsupported(items: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"[MCP 内容不支持直接显示: {item['type']}"
        + (f",引用={item['reference']}" if item["reference"] else "")
        + "]"
        for item in items
    )


def extract_result(result: Any) -> McpCallResult:
    """Extract text and explicit diagnostics for every MCP content block."""
    parts: list[str] = []
    unsupported: list[dict[str, Any]] = []
    for block in getattr(result, "content", []) or []:
        text, descriptor = _classify_block(block)
        if descriptor is not None:
            unsupported.append(descriptor)
        elif text is not None:
            parts.append(text)
    text_body = "\n".join(parts).strip()
    if unsupported:
        suffix = _render_unsupported(unsupported)
        text_body = f"{text_body}\n{suffix}" if text_body else suffix
    return McpCallResult(
        text_body,
        {
            "completeness": "unsupported" if unsupported else "complete",
            "unsupported_blocks": unsupported,
            "artifact_ref": next(
                (item["reference"] for item in unsupported if item["reference"]),
                None,
            ),
            "source": "mcp",
        },
    )


def extract_text(result: Any) -> str:
    """文本投影,供只需要字符串的调用方使用。"""
    return extract_result(result).text
