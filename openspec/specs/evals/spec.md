# evals Specification

## Purpose

定义离线端到端评测能力:用脚本化 fake 模型驱动真实 Agent 循环，在临时工作区内验证工具流、错误呈现、审批阻断与改参传播等可观察行为，作为行为回归的补充门禁。

## Requirements

### Requirement: 离线评测用例与运行入口

系统 SHALL 提供离线评测入口(`python -m evals`)，每个用例 SHALL 在独立临时工作区内通过真实 Agent 循环执行，使用 fake 模型与假工作区，不得依赖网络、真实凭据或用户目录。用例 SHALL 以稳定名称标识，单用例失败 SHALL 不阻塞其余用例，运行结果 SHALL 汇总通过/失败并以非零退出码表达失败。评测套件 SHALL 被纳入 `contract` 测试门禁，防止用例失效后无人察觉。

#### Scenario: 运行评测套件

- **WHEN** 执行 `python -m evals`
- **THEN** 逐个运行用例，输出每个用例的 PASS/FAIL 与汇总，全部通过时退出码为 0

#### Scenario: 单用例失败不影响其余

- **WHEN** 某个用例断言失败或超时
- **THEN** 记录其失败原因并继续运行其余用例，最终以非零退出码结束

#### Scenario: 评测纳入测试门禁

- **WHEN** 运行 `pytest -m contract`
- **THEN** 评测套件作为契约测试执行，任一用例失败即测试失败

#### Scenario: 覆盖关键行为

- **WHEN** 评测套件运行
- **THEN** 至少覆盖工具正常执行、未知工具错误、审批门禁阻断与前置钩子改参四类行为
