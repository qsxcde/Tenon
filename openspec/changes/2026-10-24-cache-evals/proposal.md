# 缓存观测与离线评测框架

## Why

prompt cache 命中率此前只作为 usage 数字展示,没有诊断码,也没有对"系统提示词前缀是否可缓存"的回归保护;项目缺少可在 CI 中运行、覆盖真实 Agent 循环的端到端评测,行为回归只能依赖分散的单测。

## What Changes

- 新增 `core/context/cache.py`:`CacheObservation` 聚合 usage(`input_tokens` / `cached_tokens`)产出命中率与诊断码(`cache_unknown` / `cache_cold` / `cache_effective`),并提供易变前缀检测(时间戳、临时目录);`--context` 诊断输出命中率与诊断码。
- 新增契约测试锁定"基础系统提示词不含易变标记",避免前缀变动导致缓存永久失效。
- 新增 `evals/` 离线评测框架:`uv run python -m evals` 用 fake 模型驱动真实 Agent 循环,覆盖工具流、未知工具、审批阻断与改参传播;`tests/test_evals.py` 将其纳入 `contract` 门禁。

## Capabilities

### New Capabilities

- `evals`: 离线端到端评测用例集合与运行入口。

### Modified Capabilities

- `context-diagnostics`: 新增缓存命中率观测与稳定前缀诊断。

## Impact

- 影响 `core/context/cache.py`(新增)、`app/context_diagnostics.py`、`evals/`(新增)、`tests/`。
- 不改变请求协议与 provider 缓存控制(仍由 provider/API 形状决定)。
- 评测全部离线:fake 模型 + `tmp_path` 工作区。
