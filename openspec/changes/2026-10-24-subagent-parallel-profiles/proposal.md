# Subagent 并行与可写 Profile

## Why

Subagent 运行器仅支持串行单层只读委派(`core/subagent/policy.py` 的 MVP 深度约束、`SerialSubagentRunner`、`profiles.py` 仅 explore/review),父 Agent 无法并行收集多路证据,也无法把实现类子任务交给独立上下文;生态实践(harness 的 capability seam、pi-subagent 的 spawn/steer/wait)表明有界并发与受限可写角色是委派能力的关键缺口。

## What Changes

- runner 引入有界并发槽位:默认容量 1(行为与既有串行完全一致),容量 N>1 时最多 N 个子运行并发;准入顺序、预算、取消、终态归因与有界清理保持不变。
- 新增 `implement` 可写 profile:工具集 read/write/edit/bash/grep/find/ls/skill,禁止 `delegate` 与 MCP;profile 校验 fail-closed(只读 profile 不得含改工作区工具,可写 profile 工具集必须与 `WRITABLE_TOOL_NAMES` 一致)。
- 新增配置项 `subagent_max_concurrency`(默认 1)与 `create_subagent_runner` 工厂;TUI/会话装配按配置选择 runner。

## Capabilities

### Modified Capabilities

- `subagent-runtime`: 串行独立子运行改为有界并发槽位;profile 装配新增受限可写角色。

## Impact

- 影响 `app/composition/subagent/`(runner 基类/工厂/profiles)、`app/composition/session/`(runner 选择)、`app/composition/tui/config.py`、`app/config.py`。
- 默认配置保持串行,不改变既有运行时行为;`implement` 为新增可选 profile。
- 并发写同一文件由进程级路径锁串行化;测试全部离线(假子 Session)。
