"""web_fetch 原子工具:抓取 URL 内容并返回治理后的文本。

设计(design web-todo-tools D2):
- 网络经注入的 ``fetcher``(缺省 urllib 实现),离线测试注入假实现,
  工具本身不绑定真实网络;
- 仅允许 http/https,不放行 file:// 等本地 scheme;
- 响应读取有界(不无界物化),输出按工具上限截断并携带完整性事实。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from tenon.tools.base import AtomicTool
from tenon.tools.shared import OutputPolicy, govern_text

__all__ = [
    "AsyncFetcher",
    "DEFAULT_FETCH_MAX_BYTES",
    "DEFAULT_FETCH_TIMEOUT",
    "Fetcher",
    "WebFetchTool",
]

#: 单次抓取的响应读取上限:超大响应不无界物化。
DEFAULT_FETCH_MAX_BYTES = 2_000_000
#: 默认网络超时(秒)。
DEFAULT_FETCH_TIMEOUT = 30.0

#: 注入的同步抓取函数:URL → 文本内容(实现方负责超时与网络错误)。
Fetcher = Callable[[str], str]
#: 注入的异步抓取函数:URL → 文本内容(取消时中断连接)。
AsyncFetcher = Callable[[str], Awaitable[str]]


def _urllib_fetch(url: str) -> str:
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "tenon"})
    with urllib.request.urlopen(request, timeout=DEFAULT_FETCH_TIMEOUT) as response:
        data = response.read(DEFAULT_FETCH_MAX_BYTES)
    return data.decode("utf-8", errors="replace")


async def _httpx_fetch_async(url: str) -> str:
    """可取消的默认异步抓取;取消时 httpx 中断连接。"""
    import httpx

    async with httpx.AsyncClient(timeout=DEFAULT_FETCH_TIMEOUT, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "tenon"})
        response.raise_for_status()
        return response.text[:DEFAULT_FETCH_MAX_BYTES]


class WebFetchArgs(BaseModel):
    url: str = Field(description="要抓取的 http/https URL")


class WebFetchTool(AtomicTool[WebFetchArgs]):
    name = "web_fetch"
    description = "抓取网页内容并返回文本(仅 http/https;输出按上限截断)。"
    Args = WebFetchArgs

    #: 默认异步路径经 httpx，取消时可中断连接。
    supports_cancellation = True

    def __init__(
        self,
        cwd=None,
        ops=None,
        resource_limits=None,
        fetcher: Fetcher | None = None,
        async_fetcher: AsyncFetcher | None = None,
    ) -> None:
        super().__init__(cwd=cwd, ops=ops, resource_limits=resource_limits)
        self._fetcher = fetcher if fetcher is not None else _urllib_fetch
        self._async_fetcher = async_fetcher if async_fetcher is not None else _httpx_fetch_async

    def _invoke(self, args: WebFetchArgs) -> str:
        url = _validated_url(args.url)
        try:
            body = self._fetcher(url)
        except (OSError, ValueError) as exc:
            raise ValueError(f"抓取失败: {url}: {exc}")
        return self._govern(url, body)

    async def ainvoke(self, args: WebFetchArgs) -> str:
        """可取消路径:异步抓取,取消时中断网络连接。"""
        url = _validated_url(args.url)
        try:
            body = await self._async_fetcher(url)
        except (OSError, ValueError) as exc:
            raise ValueError(f"抓取失败: {url}: {exc}")
        return self._govern(url, body)

    def _govern(self, url: str, body: str) -> str:
        return govern_text(
            body,
            OutputPolicy(max_bytes=self.output_max_bytes, max_lines=self.output_max_lines),
            url=url,
            source="web_fetch",
        )


def _validated_url(raw: str) -> str:
    url = raw.strip()
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"仅支持 http/https URL: {url}")
    return url
