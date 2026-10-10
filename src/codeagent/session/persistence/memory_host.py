"""内存存储 mixin 组合的宿主属性声明基类。

``MemoryStore``（``memory_store.py``）由恢复与元数据两个 mixin 组合而成。本基类
只提供类级类型注解，不含任何赋值或方法体；宿主 ``__init__`` 的真实赋值会覆盖
这里的声明，因此运行时行为不变。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from codeagent.core.contracts.messages import Message
    from codeagent.session.persistence.models import SessionRef


class MemoryStoreHost:
    """声明 mixin 组合宿主 ``MemoryStore`` 的共享实例属性。"""

    _sessions: dict[str, SessionRef]
    _messages: dict[str, list[Message]]
    _meta: dict[str, dict[str, Any]]


__all__ = ["MemoryStoreHost"]
