"""web_fetch 原子工具:抓取 URL 内容并返回治理后的文本。

设计(design web-todo-tools D2):
- 网络经注入的 ``fetcher``(缺省 urllib 实现),离线测试注入假实现,
  工具本身不绑定真实网络;
- 仅允许 http/https,不放行 file:// 等本地 scheme;
- 响应读取有界(不无界物化),输出按工具上限截断并携带完整性事实。
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field

from codeagent.tools.base import AtomicTool
from codeagent.tools.shared import OutputPolicy, govern_text

__all__ = ["DEFAULT_FETCH_MAX_BYTES", "DEFAULT_FETCH_TIMEOUT", "Fetcher", "WebFetchTool"]

#: 单次抓取的响应读取上限:超大响应不无界物化。
DEFAULT_FETCH_MAX_BYTES = 2_000_000
#: 默认网络超时(秒)。
DEFAULT_FETCH_TIMEOUT = 30.0

#: 注入的抓取函数:URL → 文本内容(实现方负责超时与网络错误)。
Fetcher = Callable[[str], str]


def _urllib_fetch(url: str) -> str:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "codeagent"})
    with urllib.request.urlopen(request, timeout=DEFAULT_FETCH_TIMEOUT) as response:
        data = response.read(DEFAULT_FETCH_MAX_BYTES)
    return data.decode("utf-8", errors="replace")


class WebFetchArgs(BaseModel):
    url: str = Field(description="要抓取的 http/https URL")


class WebFetchTool(AtomicTool[WebFetchArgs]):
    name = "web_fetch"
    description = "抓取网页内容并返回文本(仅 http/https;输出按上限截断)。"
    Args = WebFetchArgs

    def __init__(
        self,
        cwd=None,
        ops=None,
        resource_limits=None,
        fetcher: Fetcher | None = None,
    ) -> None:
        super().__init__(cwd=cwd, ops=ops, resource_limits=resource_limits)
        self._fetcher = fetcher if fetcher is not None else _urllib_fetch

    def _invoke(self, args: WebFetchArgs) -> str:
        url = args.url.strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"仅支持 http/https URL: {url}")
        try:
            body = self._fetcher(url)
        except (OSError, ValueError) as exc:
            raise ValueError(f"抓取失败: {url}: {exc}")
        return govern_text(
            body,
            OutputPolicy(max_bytes=self.output_max_bytes, max_lines=self.output_max_lines),
            url=url,
            source="web_fetch",
        )
