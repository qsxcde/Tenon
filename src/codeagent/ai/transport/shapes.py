"""API 形状注册表:把"线上协议形状"与"provider 端点/鉴权"解耦。

provider 只声明 endpoint、鉴权与模型目录;线上协议形状(消息/工具/流式/
思考字段的编码方式)由 API 形状描述。新增同形状 provider 不需要改 transport,
新增形状只需在此登记一条描述并在 ``ai/transport/`` 提供实现。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "API_SHAPES",
    "ApiShape",
    "DEFAULT_API_SHAPE",
    "OPENAI_COMPLETIONS",
    "register_api_shape",
    "resolve_api_shape",
    "supported_api_shapes",
]

OPENAI_COMPLETIONS = "openai-completions"
DEFAULT_API_SHAPE = OPENAI_COMPLETIONS


@dataclass(frozen=True, slots=True)
class ApiShape:
    """一种线上协议形状及其能力声明。"""

    name: str
    #: 该形状的 transport 实现位置(诊断与文档用,不参与运行时装配)。
    transport: str
    supports_streaming: bool = True
    supports_tools: bool = True
    #: 是否支持思考强度字段;不支持时 provider 配置不应发送。
    supports_reasoning: bool = False


_API_SHAPES: dict[str, ApiShape] = {
    OPENAI_COMPLETIONS: ApiShape(
        name=OPENAI_COMPLETIONS,
        transport="codeagent.ai.transport.openai_compat",
        supports_streaming=True,
        supports_tools=True,
        supports_reasoning=True,
    ),
}

#: 注册表视图(只读用途:诊断、文档与测试;写入必须走 register_api_shape)。
API_SHAPES = _API_SHAPES


def supported_api_shapes() -> tuple[str, ...]:
    return tuple(_API_SHAPES)


def resolve_api_shape(name: str | None) -> ApiShape:
    """解析 API 形状;未知形状 fail-closed(不静默回退默认值)。"""
    resolved = name or DEFAULT_API_SHAPE
    shape = _API_SHAPES.get(resolved)
    if shape is None:
        raise ValueError(
            f"不支持的 API 形状: {resolved};可用形状: {', '.join(supported_api_shapes())}"
        )
    return shape


def register_api_shape(shape: ApiShape) -> None:
    """登记一种 API 形状;重复登记 fail-closed。"""
    if not isinstance(shape, ApiShape):
        raise TypeError("API 形状必须是 ApiShape")
    if shape.name in _API_SHAPES:
        raise ValueError(f"API 形状重复登记: {shape.name}")
    _API_SHAPES[shape.name] = shape
