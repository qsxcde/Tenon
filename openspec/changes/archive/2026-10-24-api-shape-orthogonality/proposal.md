# API 形状与 Provider 正交

## Why

全部 provider 都经由同一条 OpenAI-compatible transport,provider 配置与线上协议形状耦合:新增同形状 provider 需要理解 transport,接入原生形状(anthropic-messages / responses)需要改动 provider 实现。生态实践(pi 的 `KnownApi` 与 provider 正交)表明应把"形状适配"与"端点/鉴权"拆成两层。

## What Changes

- 新增 `ai/transport/shapes.py` API 形状注册表(`ApiShape` 能力描述、`resolve_api_shape` fail-closed、`register_api_shape` 防重复)。
- `ProviderDefinition` 增加 `api_shape` 字段并在构造时校验;内置 provider 可经模块级 `API_SHAPE` 声明。
- `ai/providers/all.py` 新增 `register_provider` / `provider_definition` / `provider_definitions` 注册入口,重复 id 拒绝且不覆盖内置项。

## Capabilities

### Modified Capabilities

- `ai-provider-isolation`: 新增「API 形状与 provider 正交」需求。

## Impact

- 影响 `ai/transport/shapes.py`(新增)、`ai/providers/base.py`、`ai/providers/all.py`、`ai/providers/__init__.py`。
- 默认形状 `openai-completions` 与原行为一致;接入新形状只登记描述 + 提供实现,不改 provider。
- 测试全部离线,不依赖真实网络或凭据。
