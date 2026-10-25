# Tasks

- [x] 1.1 `core/context/contracts.py`:`BeforeToolCall` 返回类型扩为 `ToolCall | ToolDecision | None`(通知/改参/门禁)
- [x] 1.2 新建 `core/orchestration/tool_hooks.py`:`run_pre_chain`(顺序/改参传播/短路/warning 累积)与 `run_post_chain`(变换/保留)
- [x] 1.3 `core/orchestration/config.py` + `tool_call.py`:字段改名 `before_tool_calls`/`after_tool_calls` 元组并接入链执行
- [x] 1.4 `session/runtime/execution.py` + `app/composition/runtime/`(extensions/factory):policy 门禁挂链尾,装配迁移
- [x] 1.5 瀑布语义测试 + 既有钩子测试原子迁移(行为断言不变)
- [x] 2.1 `tools/plugins/manifest.py` + `loader.py`:manifest 校验、`TOOL_SPECS` 加载、`ext__<id>__<name>` 命名、失败诊断不阻塞
- [x] 2.2 `tools/plugins/permissions.py` + `tools/security/permission_rules.py`:三级规则、glob 匹配 mcp/ext 共用
- [x] 2.3 `tools/security/classifier.py`:`ext__*` 分类分支(默认 ask,fail-closed);`app/composition/policy.py` 注入 ext_rules;`app/config.py` 增 extensions_dir()
- [x] 2.4 `app/composition/runtime/tool_assembly.py`:合并内建+插件+MCP 工具与诊断
- [x] 2.5 插件契约/分类/装配测试(离线假插件)
- [x] 3.1 delta 合入 `openspec/specs/`,更新 docs/wiki,全量测试与门禁
