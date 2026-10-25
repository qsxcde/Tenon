"""provider 注册和工厂的最小类型定义。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, TypeAlias

from tenon.ai.model.protocols import ChatClient
from tenon.ai.transport.shapes import DEFAULT_API_SHAPE, resolve_api_shape

ProviderFactory: TypeAlias = Callable[..., ChatClient]


@dataclass(frozen=True)
class ProviderDefinition:
    """一个内置 provider 的显式注册描述。

    ``api_shape`` 声明线上协议形状;未知形状在构造时即 fail-closed,
    避免装配到运行时才失败。provider 只负责端点、鉴权与模型目录。
    """

    provider_id: str
    factory: ProviderFactory
    api_shape: str = DEFAULT_API_SHAPE

    def __post_init__(self) -> None:
        if not self.provider_id or not self.provider_id.strip():
            raise ValueError("provider_id 不能为空")
        resolve_api_shape(self.api_shape)

    def create_client(self, **kwargs: Any) -> ChatClient:
        return self.factory(**kwargs)
