## 1. bash 合并输出上限

- [x] 1.1 在 stdout/stderr 合并后按 `effective_output_bytes` 统一截断,标记 `merged_budget` 并更新 `shown_bytes`/`shown_lines`/`completeness`。
- [x] 1.2 删除未使用的 `MAX_OUTPUT_CHARS` 常量与导出,确认无引用残留。
- [x] 1.3 覆盖超限场景:双流均超限、仅单流超限、合并后恰好等于上限,断言元数据与正文一致。

## 2. token 估算口径

- [x] 2.1 在 core 提供中英混合估算函数(CJK 按字、其余按 4 字符),作为预算快照的唯一实现。
- [x] 2.2 压缩策略复用同一实现,删除本地 `len // 4` 副本。
- [x] 2.3 覆盖纯中文、纯英文、中英混合与空文本,断言中文误差在可接受范围且英文不回归。

## 3. 回归与验收

- [x] 3.1 新增工具级回归:40KB stdout + 40KB stderr 的合并结果不超过上限,且 `truncated_by="merged_budget"`。
- [x] 3.2 新增预算回归:中文会话的估算值显著高于旧口径,preflight 在小窗口下能判定 `over_limit`。
- [x] 3.3 运行 `tests/tools`、`tests/core`、`tests/session` 相关窄测试与快速质量集。

## 4. 文档与规格

- [x] 4.1 更新 `openspec/specs/tools/spec.md` 的「输出截断」与 `openspec/specs/context-budget/spec.md` 的「模型请求预算组成」要求。
- [x] 4.2 更新 `docs/design/roadmap-v0.6.md` 验收状态与 `CHANGELOG.md`。
- [x] 4.3 运行 `ruff check`、`ruff format --check`、`scale_scan`、`type_scan` 与 `openspec validate`。
