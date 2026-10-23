"""把多流工具输出合并后的统一上限抽成可复用的纯函数。

bash 的 stdout 与 stderr 各自按单流上限截断,因此同时写两个流的命令
可能把接近两倍的文本交给模型。本模块在合并后再次应用一次统一上限,
并保留尾部(错误信息通常在末尾),同时维护结构化事实。
"""

from __future__ import annotations

from typing import Any

from .truncate import truncate_tail

__all__ = ["MERGED_TRUNCATION_MARKER", "cap_merged_output"]

#: 合并后再次超限时的标记;区别于单流截断原因。
MERGED_TRUNCATION_MARKER = "\n...[合并输出超过统一上限,已保留末尾]..."


def cap_merged_output(
    content: str,
    output_metadata: dict[str, Any],
    *,
    max_bytes: int,
    max_lines: int,
    reason: str = "merged_budget",
) -> tuple[str, dict[str, Any]]:
    """Bound merged multi-stream output and report why it was cut.

    ``incomplete`` (timeout / cleanup uncertainty) is a stronger state than
    plain truncation and is never overwritten by this second pass.
    """
    if len(content.encode("utf-8")) <= max_bytes:
        return content, output_metadata
    marker_bytes = len(MERGED_TRUNCATION_MARKER.encode("utf-8"))
    bounded, truncation = truncate_tail(
        content,
        max_lines=max_lines,
        max_bytes=max(1, max_bytes - marker_bytes),
    )
    shown = bounded + MERGED_TRUNCATION_MARKER
    updated = dict(output_metadata)
    updated.update(
        {
            "completeness": (
                "incomplete" if output_metadata.get("completeness") == "incomplete" else "truncated"
            ),
            "truncated_by": reason,
            "shown_bytes": len(shown.encode("utf-8")),
            "shown_lines": len(shown.splitlines()),
            "merged_total_bytes": output_metadata.get("total_bytes"),
            "total_bytes": max(
                int(output_metadata.get("total_bytes") or 0),
                truncation.total_bytes,
            ),
        }
    )
    return shown, updated
