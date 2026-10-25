# Tasks

- [x] 1.1 `tools/execution/sandbox.py`:三档策略、Seatbelt/bwrap 计划、无后端 fail-closed
- [x] 1.2 `ProcessRequest.argv_prefix` + `BashTool` 按策略构造请求
- [x] 1.3 `app/config.py`:`sandbox_policy` 配置与校验;registry 注入策略
- [x] 2.1 `tools/shared/checkpoints.py`:`CheckpointStore`(快照/索引/淘汰/LIFO 恢复)
- [x] 2.2 `write`/`edit` 在锁内写入前记录快照;registry 注入 store
- [x] 2.3 `tenon undo` 子命令(`--list` / `--dry-run` / 恢复)
- [x] 2.4 测试:沙箱计划与 fail-closed、checkpoint 语义、write/edit 集成、CLI
- [x] 2.5 更新 `openspec/specs/tools/spec.md` 与文档
