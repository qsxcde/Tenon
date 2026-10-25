# 06 · ai 层：模型提供商与传输

> ai 层负责"把一次模型请求发出去、把流式响应收回来、把失败分类清楚"，并通过静态模型目录提供元数据。它不感知会话历史、工具执行或 UI；对 core 的依赖仅通过 `app/composition/model` 的转换器完成。

## 一、层内地图

| 模块 | 职责 | 关键内容 |
| --- | --- | --- |
| `ai/model/protocols.py` | 模型侧协议 | `ChatClient`、`Transport`、`Provider` |
| `ai/model/types.py` | 传输用中性类型 | `ChatMessage`、`ToolCall`、`ToolDefinition`、`ChatResponse`、`StreamEvent`、`StreamEventType`、`Usage` |
| `ai/providers/*` | 内置 provider 配置 + 工厂 | 6 个真实 provider + 1 个 `fake` |
| `ai/providers/base.py` | 注册类型 | `ProviderDefinition`、`ProviderFactory` |
| `ai/transport/shapes.py` | API 形状注册表 | `ApiShape`、`resolve_api_shape`（未知 fail-closed）、`register_api_shape` |
| `ai/transport/openai_compat.py` | OpenAI 兼容 HTTP 客户端 | `OpenAICompatClient` |
| `ai/transport/sse.py` | SSE 解析 | `SSEParser` |
| `ai/transport/streaming.py` | 流式消费与重试规则 | 首事件后不重放 |
| `ai/transport/retry.py` | 重试参数 | 退避与上限常量 |
| `ai/errors.py` | 错误分类与脱敏 | `ProviderError`、`ProviderHTTPError`、`classify_provider_error` |
| `ai/catalog/spec.py` | 模型规格 | `ModelSpec` |
| `ai/catalog/builtin.py` | 内置模型清单 | `BUILTIN_CATALOGS` 及各 provider 的模型字典 |
| `ai/catalog/store.py` | 用户模型覆盖 | `ModelStore`（双拼写 upsert） |
| `ai/catalog/registry.py` | 解析与查找 | `ModelRegistry`（精确 id → 别名两遍解析） |

依赖方向：`providers → transport`、`providers → catalog`、`transport → errors`、`catalog → spec`。`ai` 不导入 `core`、`session`、`tools`、`app`；`ai/__init__.py` 只再导出模型契约与错误类型。core 的 `Message` 与 ai 的 `ChatMessage` 之间的转换发生在组合根 [`app/composition/model/port.py`](../../src/tenon/app/composition/model/port.py) 的 `to_chat_message`，因此 ai 层对 core 零依赖。

## 二、模型契约（ai/model）

### 2.1 协议

| 协议 | 方法 | 说明 |
| --- | --- | --- |
| `Transport` | `generate(messages, tools=None, *, stream=False)`、`stream(messages, tools=None) -> AsyncIterator[StreamEvent]`、`aclose()` | 模型传输实现的最小调用面 |
| `ChatClient` | 继承 `Transport`，扩展 `model_id` 属性与 `bind_tools(tools)` | Agent loop 依赖的统一客户端协议 |
| `Provider` | `provider_id` 属性、`create_client(*, model, reasoning_effort=None, **kwargs)` | 预留的对象化注册协议；当前内置 provider 走函数工厂注册表 |

核心代码只依赖 `ChatClient` 协议（与 core 的 `ModelPort` 结构兼容），因此 `OpenAICompatClient`、fake provider 与测试替身可无缝互换。

### 2.2 传输类型

| 类型 | 字段要点 |
| --- | --- |
| `ChatMessage` | `role` / `content`（`str` 或内容块列表）/ `tool_calls` / `tool_call_id` / `name`；`to_api_dict()` 输出 wire 格式（有 tool_calls 时 content 保留 `None`，不丢失非空旁白） |
| `ToolCall` | `id` / `name` / `arguments`（字符串） |
| `ToolDefinition` | `name` / `description` / `parameters`；`to_api_dict()` 生成 `{"type": "function", "function": {...}}` |
| `ChatResponse` | 非流式/流式汇总结果：`content` / `tool_calls` / `usage: dict \| None` / `finish_reason` / `model` |
| `StreamEvent` | 流式增量：`type` / `content` 片段 / `tool_call` 增量 / `usage: dict \| None` |
| `StreamEventType` | `Literal["content", "thinking", "tool_call_arg", "finish", "usage"]` |

`usage` 以原始字典透传（不建模型类），字段名由 provider 决定；流式回合的用量依赖请求侧开启 `stream_options={"include_usage": True}`，否则 provider 不会在流末尾返回用量。

## 三、provider 体系

### 3.1 内置 provider 一览

每个 provider 模块导出 `PROVIDER_NAME`、一个 `BaseSettings` 配置类（`env_prefix` 决定环境变量命名空间）和 `make_llm(cfg, spec, *, reasoning_effort)` 工厂。工厂在缺 key 时报"可操作错误"，而不是底层 SDK 的凭据异常。

| provider_id | 配置类 | env 前缀 | 默认 base_url | 默认模型 | `reasoning_effort` 默认 |
| --- | --- | --- | --- | --- | --- |
| `deepseek` | `DeepSeekConfig` | `DEEPSEEK_` | `https://api.deepseek.com` | `deepseek-v4-flash` | `high` |
| `openai` | `OpenAIConfig` | `OPENAI_` | `https://api.openai.com/v1` | `gpt-5-nano` | `high` |
| `qwen` | `QwenConfig` | `QWEN_` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.8-max` | `None`（不发送） |
| `glm` | `GlmConfig` | `GLM_` | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.2` | `None`（不发送） |
| `kimi` | `KimiConfig` | `KIMI_` | `https://api.moonshot.cn/v1` | `kimi-k3` | `high` |
| `minimax` | `MiniMaxConfig` | `MINIMAX_` | `https://api.minimaxi.com/v1` | `MiniMax-M3` | `None`（不发送） |
| `fake` | 无 | — | 内存 | 脚本化 | — |

- 配置字段统一为 `api_key`（`SecretStr`，repr/日志不泄密）、`base_url`、`model`，另有 provider 特有字段（如 `reasoning_effort`）。
- `reasoning_effort` 默认 `None` 表示"该兼容层未确认支持，不发送"；即使配置了值，工厂仍会先看 `ModelSpec.reasoning` 再决定是否透传。
- `extra="ignore"`：同一进程内的多个 provider 共享环境变量空间，无关变量不报错。
- 注册表在 `ai/providers/all.py`：`BUILTIN_PROVIDERS`（有序元组）、`PROVIDERS`（id → 工厂）、`PROVIDER_CONFIGS`（id → 配置类）。`fake` 只出现在 `PROVIDERS`，不出现在 `PROVIDER_CONFIGS`。
- **API 形状与 provider 正交**：`ProviderDefinition.api_shape` 声明线上协议形状（默认 `openai-completions`），构造期经 `resolve_api_shape` 校验、未知形状 fail-closed。新增同形状 provider 只需绑端点/鉴权/模型目录；新形状经 `register_api_shape` 登记并在 `ai/transport/` 提供实现。自定义 provider 经 `register_provider(definition, config_cls)` 注册，重复 id 拒绝且不覆盖内置项。
- 工厂按 `ModelSpec.reasoning` 决定是否透传 `reasoning_effort`（单次覆盖参数 > 配置默认值），非推理模型忽略该参数。

### 3.2 fake provider

`ai/providers/fake.py` 提供脚本化 `FakeClient`，是全部离线测试与 CLI smoke 的模型替身：

- 按预置 `steps`/`responses` 顺序返回；每个 step 可带 `content`、`tool_calls`、`usage`。
- `call_history` 记录每次请求的消息与工具定义，用于断言上下文组装。
- 支持 `stream()` 顺序产出与 `complete()` 一致的脚本化流。
- 测试侧入口在 `tests/fixtures/ai.py`（构造器 + `FakeClient`）。

## 四、传输与流式

### 4.1 OpenAICompatClient

构造校验：`base_url` 必须是带主机名的 http/https URL 且不含 query/fragment（否则 `ValueError`）；`max_tokens` 若给必须为正整数；`reasoning_effort` 若给必须属于 `low/medium/high/xhigh/max/ultra`；`max_retries` 经 `validate_max_retries` 限 0..5。请求端点固定为 `{base_url}/chat/completions`，base_url 会 `rstrip("/")` 归一。超时默认：

| 阶段 | 默认值 |
| --- | --- |
| `connect` | 10s |
| `read` | 120s（流式时 `read=None`，长回答不中断） |
| `write` | 30s |
| `pool` | 10s |

- 请求体由 `ChatMessage.to_api_dict()` / `ToolDefinition.to_api_dict()` 组装，`tool_choice` 与 `reasoning_effort` 按需附带。
- 所有 HTTP 失败经 `classify_provider_error` 归一为 `ProviderError`（或兼容 `httpx.HTTPStatusError` 的 `ProviderHTTPError`），上层只面对统一错误面。
- 流式响应交由 `streaming.py` 消费；工具调用参数在流中以 `tool_call_arg` 增量到达，由 `SSEParser.assembled_tool_calls()` 在 `finish` 时聚合。

### 4.2 SSEParser

`ai/transport/sse.py` 的 `SSEParser.feed(chunk)` 增量解析 `data:` 行，产出 `StreamEvent`：

| 事件 | 来源 |
| --- | --- |
| `content` | `delta.content` |
| `thinking` | `delta.reasoning_content`（推理模型的思维链） |
| `tool_call_arg` | `delta.tool_calls[*]` 的分片参数 |
| `finish` | `finish_reason` |
| `usage` | 尾部 `usage` 块（需 `include_usage`） |

解析器对不完整行、`[DONE]` 哨兵与空 data 做了容错，不抛解析异常。

### 4.3 重试语义

`ai/transport/retry.py`：

| 常量 | 值 | 含义 |
| --- | --- | --- |
| `DEFAULT_MAX_RETRIES` | 3 | 默认最大重试次数 |
| `MAX_RETRIES` | 5 | 硬上限（配置超过会校验失败） |
| `MAX_RETRY_DELAY` | 10.0s | 指数退避封顶 |

规则：

1. 只有 `retryable=True` 的错误（network / timeout / rate_limit / server）与 `408` 参与重试。
2. `Retry-After` 响应头优先于指数退避；`MAX_RETRY_DELAY` 封顶。
3. **流式请求一旦收到首个事件就不再重放**——避免重复的内容/工具副作用；此时失败直接上抛为错误结果。
4. 非流式请求与"首事件之前"的流式失败按同一策略重试。

## 五、错误分类（ai/errors.py）

`ProviderErrorKind` 与实际分类逻辑：

| 输入 | kind | retryable |
| --- | --- | --- |
| HTTP 401 / 403 | `authentication` | 否 |
| HTTP 408 | `timeout` | 是 |
| HTTP 429 | `rate_limit` | 是 |
| HTTP ≥ 500 | `server` | 是 |
| 400 / 422 且详情匹配"参数不支持"正则 | `unsupported_parameter` | 否 |
| 其它 4xx | `invalid_request` | 否 |
| `httpx.TimeoutException` | `timeout` | 是 |
| `httpx.TransportError` | `network` | 是 |
| 其余未知异常 | `unknown` | 否 |

结构：`ProviderError` 携带 `kind` / `retryable` / `status_code` / `provider` / `model` / `request_id` / `retry_after` / `detail`；`ProviderHTTPError` 通过多重继承同时兼容 `httpx.HTTPStatusError`。

脱敏规则（`_bounded_detail`，上限 `_MAX_DETAIL_LENGTH = 1000`）：

- `Bearer <token>` → `Bearer [REDACTED]`；
- `api_key=`/`token:`/`password`/`secret`/`authorization` 等键值对的值 → `[REDACTED]`；
- 超长详情截断加 `…`；空详情归一为"无响应详情"。

响应详情提取顺序：`error.message` → `error.detail` → 序列化 `error` → 顶层 `message`/`detail` → 原始文本。

## 六、模型目录（ai/catalog）

### 6.1 ModelSpec

`ai/catalog/spec.py` 的 `ModelSpec` 是不可变、可哈希的元数据记录：

| 字段 | 说明 |
| --- | --- |
| `id` | 唯一 id（解析主键） |
| `name` | 展示名 |
| `reasoning` | 是否推理模型（决定 `reasoning_effort` 透传） |
| `max_tokens` | 输出上限 |
| `context_window` | 上下文窗口；压缩阈值与 budget 估算使用 |
| `tool_calling` | 是否支持工具调用 |
| `prompt_cache` | 是否声明提示缓存 |
| `aliases` | 别名元组（内部恒为 `tuple`，构造时接受 list） |

三个能力字段均为"严格三态"：`True` / `False` / `None`（未知）——未知时诚实展示为未知，不猜测。仓库记忆中的早期缺陷（可变 `aliases` 导致 hash 失败）已由 tuple 化修复。

### 6.2 builtin 目录与解析

- `ai/catalog/builtin.py` 定义每个 provider 的静态模型字典（如 `DEEPSEEK_MODELS`）与汇总的 `BUILTIN_CATALOGS`。目录是静态的，不依赖 `/models` 探测（`/models` 只返回 id，不携带价格/窗口等元数据）。
- `ai/catalog/store.py` 的 `ModelStore` 允许用户在 `~/.tenon` 覆盖/新增模型，兼容 camelCase 与 snake_case 双拼写 upsert。
- `ai/catalog/registry.py` 的 `ModelRegistry` 做**两遍解析**：先精确匹配 `id`，再匹配别名；仍未命中则按"未知能力"处理（构造一个仅含 id 的 `ModelSpec`）。

## 七、与其他层的关系

| 交互 | 位置 | 说明 |
| --- | --- | --- |
| 上下文消息转换 | `app/composition/model/port.py` | core `Message` → ai `ChatMessage`；工具定义序列化 |
| 模型端口适配 | `app/composition/model/` | 把 `ChatClient` 适配为 core 的 `ModelPort` |
| 客户端构造 | `app/composition/model/factory.py` | 选 provider、读配置、注入 `ModelSpec` |
| 用量与压缩 | `session` | `usage` 事件落盘；`context_window` 驱动压缩阈值 |
| 能力诊断 | `app/tui` `/status` | 展示 `reasoning`/`tool_calling`/`prompt_cache` 与窗口来源 |

## 八、设计约束

1. **ai 不知道 core**：消息与工具定义的形态转换在组合根完成，ai 只面对 wire 格式。
2. **错误必须分类且可诊断**：任何 provider 失败都要落到 `ProviderErrorKind`，禁止把原始 SDK 异常泄漏到上层。
3. **脱敏是默认行为**：详情截断与凭据掩码在 `errors.py` 单点实现，调用方不需要重复处理。
4. **重试不制造重复副作用**：流式首事件之后绝不重放（与 session 的成功才落盘闸门配套）。
5. **元数据静态化**：模型窗口/能力来自目录而非网络探测，保证离线可用与确定性。
6. **未知即未知**：能力三态不允许用默认值掩盖不确定性，上层据此决定是否允许请求（见 core 的 `uncertain_budget_policy`）。

## 相关阅读

- core 如何消费模型端口：[04-core-layer.md](./04-core-layer.md)
- 上下文预算与压缩如何用 `context_window`：[04-core-layer.md](./04-core-layer.md)、[05-session-layer.md](./05-session-layer.md)
- 依赖边界与解耦判据：[10-dependency-map.md](./10-dependency-map.md)