# Session 模块布局与迁移说明

`tenon.session` 仍保留 `AgentSession`、`SessionManager` 和 `EventBus` 这三个包级稳定导出；实现按职责归并到子包。新代码不得依赖已删除的根级兼容模块。

## 规范入口

| 能力 | 规范入口 |
|---|---|
| 事件总线 | `tenon.session.events` |
| 持久化协议、记录、内存后端和提交协调 | `tenon.session.persistence` |
| JSONL 文件后端 | `tenon.session.persistence.jsonl` |
| 会话树和分支导航 | `tenon.session.navigation` |
| 运行控制、状态、确认和事件映射 | `tenon.session.runtime` |
| 压缩 | `tenon.session.compaction` |
| 会话壳和生命周期管理 | `tenon.session`、`tenon.session.session`、`tenon.session.manager` |

持久化后端的同步文件访问、锁、索引更新和 `fsync` 由 `SessionPersistence` 的异步边界在线程中执行。异步会话运行路径应使用 `commit_turn_async()` 和 `append_compaction_async()`；同步 `commit_turn()` 仅供同步调用方使用。

## Breaking change：已删除入口

以下旧路径不再导出兼容门面，调用方必须迁移：

| 旧路径 | 替代入口 |
|---|---|
| `tenon.session.bus` | `tenon.session.events` |
| `tenon.session.store` | `tenon.session.persistence` |
| `tenon.session.memory_store` | `tenon.session.persistence.memory_store` |
| `tenon.session.json_file_store` | `tenon.session.persistence.jsonl` |
| `tenon.session.persistence.jsonl_store` | `tenon.session.persistence.jsonl` |
| `tenon.session.persistence.jsonl_reading` | `tenon.session.persistence.jsonl.reading` |
| `tenon.session.persistence.jsonl_writing` | `tenon.session.persistence.jsonl.writing` |
| `tenon.session.persistence.jsonl_indexing` | `tenon.session.persistence.jsonl.indexing` |
| `tenon.session.persistence.jsonl_forking` | `tenon.session.persistence.jsonl.forking` |
| `tenon.session.store_codec` | `tenon.session.persistence.codec` |
| `tenon.session.store_index` | `tenon.session.persistence.index` |
| `tenon.session.store_models` | `tenon.session.persistence.models` |
| `tenon.session.tree` | `tenon.session.navigation` |
| `tenon.session.session_runtime` | `tenon.session.runtime` |

这是有意的 breaking change：旧路径导入失败，避免新增代码继续绕过职责边界。迁移后请优先从子包导入公开对象，例如 `from tenon.session.persistence import JsonFileStore`。
