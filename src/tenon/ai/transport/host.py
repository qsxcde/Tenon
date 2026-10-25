"""``OpenAICompatClient`` mixin 组合的宿主属性声明基类。

``OpenAICompatClient``（``openai_compat.py``）把流式请求能力委托给
``OpenAICompatStreamingMixin``（``streaming.py``）。mixin 里访问的宿主状态与
宿主方法对 mypy 不可见，逐条报 ``attr-defined``。本基类只提供类级类型注解，
不含任何赋值或方法体，因此不改变运行时行为；宿主 ``__init__`` 的真实赋值与
方法定义会覆盖这里的声明。
"""

from __future__ import annotations

from typing import Any, Callable

import httpx


class OpenAICompatClientHost:
    """声明 mixin 组合宿主 ``OpenAICompatClient`` 的共享实例属性。"""

    # 宿主 ``__init__`` 建立的实例状态。
    _model: str
    _provider: str | None
    _max_retries: int
    _stream_timeout: httpx.Timeout

    # 定义在宿主、但被 mixin 调用的方法;用 ``Callable`` 注解声明调用面,
    # 避免与宿主的方法定义产生 override 签名冲突。
    _body: Callable[..., dict[str, Any]]
    _get_client: Callable[..., httpx.AsyncClient]
    _endpoint: Callable[..., str]
    _headers: Callable[..., dict[str, str]]
