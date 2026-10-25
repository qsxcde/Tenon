# Tasks

- [x] 1.1 `app/composition/subagent/runner_base.py`:并发门(Semaphore)承载准入/执行/归因逻辑
- [x] 1.2 `app/composition/subagent/runner.py`:`SerialSubagentRunner`(容量 1)与 `ParallelSubagentRunner`(容量 ≥2)
- [x] 1.3 `app/composition/subagent/factory.py` + session/tui 装配:按 `subagent_max_concurrency` 选择 runner
- [x] 2.1 `profiles.py`:新增 `implement` 可写 profile + fail-closed 校验(只读禁写工具、可写禁 delegate)
- [x] 2.2 测试:并行峰值/容量/取消隔离、profile 契约迁移
- [x] 2.3 更新 `openspec/specs/subagent-runtime/spec.md` 与文档
