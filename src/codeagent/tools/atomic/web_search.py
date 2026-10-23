"""web_search 原子工具:经注入的搜索提供方检索网页。

设计(design web-todo-tools D3):
- 搜索后端不内置(无默认密钥/服务):``searcher`` 由组合根注入,
  未注入时返回明确的不可用提示(skill 工具同款语义);
- 提供方返回已格式化的结果行,工具只做上限治理,不解析具体服务协议。
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from codeagent.tools.base import AtomicTool
from codeagent.tools.shared import OutputPolicy, govern_text

__all__ = ["DEFAULT_LIMIT", "Searcher", "WebSearchTool"]

#: 单次搜索默认返回的结果条数。
DEFAULT_LIMIT = 5

#: 注入的搜索函数:(查询词, 条数) → 已格式化的结果行。
Searcher = Callable[[str, int], list[str]]


class WebSearchArgs(BaseModel):
    query: str = Field(min_length=1, description="搜索关键词")
    limit: int | None = Field(None, description="最多返回的结果条数,缺省 5")


class WebSearchTool(AtomicTool[WebSearchArgs]):
    name = "web_search"
    description = "搜索网页并返回结果列表(需组合根注入搜索提供方)。"
    Args = WebSearchArgs

    def __init__(
        self,
        cwd=None,
        ops=None,
        resource_limits=None,
        searcher: Searcher | None = None,
    ) -> None:
        super().__init__(cwd=cwd, ops=ops, resource_limits=resource_limits)
        self._searcher = searcher

    def _invoke(self, args: WebSearchArgs) -> str:
        if self._searcher is None:
            return (
                "web_search 不可用: 未配置搜索提供方(组合根注入 searcher 后启用)。"
                "已知 URL 可改用 web_fetch 抓取。"
            )
        limit = args.limit if args.limit is not None else DEFAULT_LIMIT
        try:
            results = self._searcher(args.query, limit)
        except (OSError, ValueError) as exc:
            raise ValueError(f"搜索失败: {args.query}: {exc}")
        if not results:
            return f"(无匹配结果: {args.query})"
        body = "\n".join(f"{index}. {line}" for index, line in enumerate(results[:limit], start=1))
        return govern_text(
            body,
            OutputPolicy(max_bytes=self.output_max_bytes, max_lines=self.output_max_lines),
            query=args.query,
            source="web_search",
        )
