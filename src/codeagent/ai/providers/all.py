"""内置 provider 的显式集合与自定义 provider 注册入口。"""

from __future__ import annotations

from codeagent.ai.providers import deepseek, fake, glm, kimi, minimax, openai, qwen
from codeagent.ai.providers.base import ProviderDefinition, ProviderFactory
from codeagent.ai.transport.shapes import DEFAULT_API_SHAPE

BUILTIN_PROVIDERS: tuple[ProviderDefinition, ...] = tuple(
    ProviderDefinition(
        provider_id=module.PROVIDER_NAME,
        factory=module.make_llm,
        api_shape=getattr(module, "API_SHAPE", DEFAULT_API_SHAPE),
    )
    for module in (deepseek, openai, qwen, glm, kimi, minimax, fake)
)

PROVIDERS: dict[str, ProviderFactory] = {
    definition.provider_id: definition.factory for definition in BUILTIN_PROVIDERS
}

PROVIDER_CONFIGS: dict[str, type] = {
    deepseek.PROVIDER_NAME: deepseek.DeepSeekConfig,
    openai.PROVIDER_NAME: openai.OpenAIConfig,
    qwen.PROVIDER_NAME: qwen.QwenConfig,
    glm.PROVIDER_NAME: glm.GlmConfig,
    kimi.PROVIDER_NAME: kimi.KimiConfig,
    minimax.PROVIDER_NAME: minimax.MiniMaxConfig,
}

_PROVIDER_DEFINITIONS: dict[str, ProviderDefinition] = {
    definition.provider_id: definition for definition in BUILTIN_PROVIDERS
}


def register_provider(definition: ProviderDefinition, config_cls: type | None = None) -> None:
    """登记自定义 provider;重复 id fail-closed,不覆盖内置项。

    自定义 provider 只需提供端点/鉴权配置与 ``make_llm`` 工厂,
    API 形状复用已登记的形状(如 ``openai-completions``)。
    """
    if not isinstance(definition, ProviderDefinition):
        raise TypeError("provider 注册项必须是 ProviderDefinition")
    if definition.provider_id in _PROVIDER_DEFINITIONS:
        raise ValueError(f"provider 已存在,不能重复注册: {definition.provider_id}")
    _PROVIDER_DEFINITIONS[definition.provider_id] = definition
    PROVIDERS[definition.provider_id] = definition.factory
    if config_cls is not None:
        PROVIDER_CONFIGS[definition.provider_id] = config_cls


def provider_definition(provider_id: str) -> ProviderDefinition:
    """按 id 取得注册描述;未知 id 明确报错。"""
    try:
        return _PROVIDER_DEFINITIONS[provider_id]
    except KeyError as exc:
        raise KeyError(f"未知 provider: {provider_id}") from exc


def provider_definitions() -> tuple[ProviderDefinition, ...]:
    """按注册顺序返回全部 provider 描述(内置 + 自定义)。"""
    return tuple(_PROVIDER_DEFINITIONS.values())


__all__ = [
    "BUILTIN_PROVIDERS",
    "PROVIDER_CONFIGS",
    "PROVIDERS",
    "provider_definition",
    "provider_definitions",
    "register_provider",
]
