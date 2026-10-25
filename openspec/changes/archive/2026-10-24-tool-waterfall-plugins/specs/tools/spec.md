# tools Specification 变更

## ADDED Requirements

### Requirement: 插件目录发现与加载

系统 SHALL 从用户插件目录(`~/.codeagent/extensions/<目录>/`)发现插件:每个插件目录 SHALL 含 `codeagent-plugin.json` manifest(id/name/version/module/tools)与 manifest 声明的 Python 模块;插件模块 SHALL 导出 `TOOL_SPECS`(与内建 `BUILTIN_TOOL_SPECS` 同构的工具注册项)。插件工具 SHALL 以 `ext__<插件id>__<工具名>` 命名空间注册,插件 id 与工具名 SHALL 匹配 `^[a-z][a-z0-9_]*$` 且不含 `__`;manifest 的 `module` 路径解析后 SHALL 仍在插件目录内,越界 SHALL 拒绝加载。单插件的任何失败(manifest 非法、import 失败、导出缺失、构建异常、id 冲突)SHALL 产生诊断并跳过该插件,不得阻塞其它插件与内建工具装配;插件目录缺失 SHALL 装配空插件集且不产生诊断。插件代码与内建工具同进程执行,SHALL 由目录放置即信任模型覆盖(用户放入插件目录 = 授权执行)。

#### Scenario: 插件工具装配

- **WHEN** 插件目录含合法 manifest 且模块导出 `TOOL_SPECS`
- **THEN** 插件工具以 `ext__<插件id>__<工具名>` 进入工具列表,与内建工具同管道适配执行

#### Scenario: 声明的模块越界拒绝

- **WHEN** manifest 的 `module` 解析后指向插件目录之外
- **THEN** 该插件不加载,产生可诊断错误,其它插件不受影响

#### Scenario: 单插件失败不阻塞

- **WHEN** 任一插件 import 或构建抛出异常
- **THEN** 系统记录该插件的失败诊断并继续装配其余工具

#### Scenario: 命名空间唯一

- **WHEN** 两个插件注册出同名工具或重复插件 id
- **THEN** 冲突项被拒绝并产生诊断,不静默覆盖

#### Scenario: 声明与实际不一致

- **WHEN** manifest 的 `tools` 声明与模块实际导出不一致
- **THEN** 系统产生诊断,但以实际导出为准装配

### Requirement: 扩展工具安全分类

安全分类器 SHALL 对 `ext__` 前缀的插件工具实施独立分类:默认 SHALL 为 ask(需用户确认,无确认通道时 fail-closed 拒绝);`~/.codeagent/extensions.json` 的 `permissions.deny/ask/allow` 三级规则(glob,优先级 deny > ask > allow)SHALL 可显式放行或拒绝;规则匹配语义 SHALL 与 MCP 权限规则一致(`ext__*`、`ext__<插件id>__*`、精确名)。插件工具 SHALL 不得通过命名或参数绕过该分类。

#### Scenario: 默认需确认

- **WHEN** 无任何权限规则命中 `ext__demo__hello`
- **THEN** 分类结论为 ask,未确认不得执行

#### Scenario: 显式放行与拒绝

- **WHEN** `extensions.json` 规则分别 allow 与 deny 命中不同插件工具
- **THEN** allow 命中直接放行、deny 命中拒绝,deny 优先于 ask/allow

#### Scenario: 无确认通道 fail-closed

- **WHEN** headless(无确认通道)下触发 ask 档插件工具
- **THEN** 调用被拒绝并给出原因,不执行插件代码
