"""API 形状注册表与 provider 正交注册契约(离线)。"""

from __future__ import annotations

import pytest

from codeagent.ai.providers.all import (
    BUILTIN_PROVIDERS,
    PROVIDERS,
    provider_definition,
    provider_definitions,
    register_provider,
)
from codeagent.ai.providers.base import ProviderDefinition
from codeagent.ai.transport.shapes import (
    DEFAULT_API_SHAPE,
    ApiShape,
    register_api_shape,
    resolve_api_shape,
    supported_api_shapes,
)


def _factory(**kwargs):
    del kwargs
    return object()


def test_default_shape_resolves():
    shape = resolve_api_shape(None)
    assert shape.name == DEFAULT_API_SHAPE
    assert shape.supports_tools and shape.supports_streaming
    assert DEFAULT_API_SHAPE in supported_api_shapes()


def test_unknown_shape_fails_closed():
    with pytest.raises(ValueError, match="不支持的 API 形状"):
        resolve_api_shape("anthropic-messages-not-installed")


def test_provider_definition_validates_shape_at_construction():
    with pytest.raises(ValueError, match="不支持的 API 形状"):
        ProviderDefinition(provider_id="custom", factory=_factory, api_shape="missing-shape")
    with pytest.raises(ValueError, match="provider_id"):
        ProviderDefinition(provider_id="", factory=_factory)


def test_every_builtin_provider_declares_a_supported_shape():
    for definition in BUILTIN_PROVIDERS:
        assert resolve_api_shape(definition.api_shape).name == definition.api_shape


def test_register_custom_provider_and_reject_duplicates():
    definition = ProviderDefinition(provider_id="acme-gateway", factory=_factory)
    register_provider(definition)
    try:
        assert provider_definition("acme-gateway") is definition
        assert "acme-gateway" in PROVIDERS
        assert "acme-gateway" in [item.provider_id for item in provider_definitions()]
        with pytest.raises(ValueError, match="不能重复注册"):
            register_provider(definition)
        with pytest.raises(ValueError, match="不能重复注册"):
            register_provider(ProviderDefinition(provider_id="deepseek", factory=_factory))
    finally:
        from codeagent.ai.providers.all import _PROVIDER_DEFINITIONS

        _PROVIDER_DEFINITIONS.pop("acme-gateway", None)
        PROVIDERS.pop("acme-gateway", None)


def test_register_new_shape_is_idempotent_guarded():
    shape = ApiShape(name="test-shape", transport="codeagent.ai.transport.test")
    register_api_shape(shape)
    assert resolve_api_shape("test-shape") is shape
    with pytest.raises(ValueError, match="重复登记"):
        register_api_shape(shape)
    with pytest.raises(TypeError, match="ApiShape"):
        register_api_shape("not-a-shape")  # type: ignore[arg-type]
