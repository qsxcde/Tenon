# 工具执行瀑布管线 + 插件目录

## Why

当前工具执行只有单点 `before_tool_call` / `after_tool_call` 钩子,无法组合多个观察者/改写者/门禁(审批、脱敏、观测各自为政);同时项目没有插件机制,第三方扩展能力只能改内建代码——生态调研(deepseek-harness "Everything is a Plugin"、pi 扩展 API)表明"有序瀑布 + 插件贡献工具"是 harness 可扩展性的核心缝隙,且工具注册表数据化(6961ace)后插件工具可直接复用 `ToolSpec`/`ToolRegistry`。

## What Changes

- **工具执行瀑布管线**:单点 before/after 钩子改为有序钩子链。pre 链支持三种语义——通知(None,继续)、改参(返回修改后的 `ToolCall`,后续钩子与执行只见新 call)、门禁(`block` 短路,产生模型可见 REJECTED 结果,不执行工具、不跑 post 链);`allow(reason, warning=True)` 放行并按序累积 warning。post 链支持结果变换/脱敏(返回替换 `ToolResult` 或 None 保留)。安全策略门禁挂在链尾,decide 与确认事件使用改参后的 call。
- **插件目录**:`~/.tenon/extensions/<dir>/tenon-plugin.json` manifest + Python 模块;v1 仅允许插件贡献工具(导出 `TOOL_SPECS`,与 `BUILTIN_TOOL_SPECS` 同构);工具名强制命名空间 `ext__<插件id>__<工具名>`;单插件失败仅产生诊断不阻塞整体;**目录放置即信任**(与 mcp.json 列出即启动进程一致)。
- **扩展工具安全分类**:`ext__*` 工具默认进 ask 档(fail-closed),可经 `~/.tenon/extensions.json` 的 `permissions.deny/ask/allow` 三级规则放行/拒绝。

## Capabilities

### New Capabilities

### Modified Capabilities

- `core`: 工具钩子契约由单点改为有序瀑布链(通知/改参/门禁 + post 变换),策略门禁位于链尾。
- `tools`: 新增「插件目录发现与加载」与「扩展工具安全分类」需求。

## Impact

- 影响 `core/context/contracts.py`、`core/orchestration/`(config/tool_call/新增 tool_hooks)、`session/runtime/execution.py`、`app/composition/runtime/`(extensions/factory/tool_assembly)、`tools/plugins/`(新增)、`tools/security/classifier.py`、`app/composition/policy.py`、`app/config.py`。
- **BREAKING**:`AgentLoopConfig.before_tool_call`/`after_tool_call` 与 `RuntimeExtensions` 同名字段改为 `before_tool_calls`/`after_tool_calls` 元组;不留兼容垫片,调用点与测试原子迁移。
- 插件代码同进程执行、无沙箱(与 MCP server 模型一致);import 期副作用属"放置即信任"范围,文档显式声明。
- 测试全部离线(tmp_path 假插件目录 + monkeypatch CONFIG_DIR)。
