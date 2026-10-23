## 1. 追加路径增量索引

- [x] 1.1 调整 `_append`:在写 JSONL 之前读取并校验索引,失败时回源重建。
- [x] 1.2 让 `apply_record` 支持"不刷新指纹",由追加路径在写完 JSONL 后统一刷新。
- [x] 1.3 保持索引写失败、`fsync` 失败与并发追加的既有语义不变。

## 2. 回归与性能

- [x] 2.1 新增回归:追加后索引 `source` 与文件指纹一致,且后续 `get()`/`load_usage()` 读取命中索引。
- [x] 2.2 新增回归:索引被外部删除/损坏后首次追加回源重建,第二次追加走增量。
- [x] 2.3 新增性能回归:1000 次追加总耗时显著低于旧口径(目标 ≤1s),并断言未发生全量重建。
- [x] 2.4 运行 `tests/session/store` 与 `tests/session/behavior` 相关窄测试。

## 3. 文档与规格

- [x] 3.1 更新 `openspec/specs/sessions/spec.md` 的「会话元数据索引可重建」要求与场景。
- [x] 3.2 更新 `docs/design/roadmap-v0.6.md` 验收状态与 `CHANGELOG.md`。
- [x] 3.3 运行 `ruff check`、`ruff format --check`、`scale_scan`、`type_scan` 与 `openspec validate`。
