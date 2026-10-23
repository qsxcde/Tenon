# tools Specification 变更

## ADDED Requirements

### Requirement: web_fetch 网页抓取

`web_fetch` 工具 SHALL 抓取 http/https URL 的内容并返回治理后的文本;仅接受 http/https scheme,其它 scheme(如 `file://`)SHALL 明确拒绝且不发起任何抓取。网络调用 SHALL 经注入的抓取函数完成,离线测试注入假实现即可运行;响应读取 SHALL 有界(不无界物化),输出按统一上限截断并携带完整性事实(url、来源、总量/展示量)。网络出站调用 SHALL 进入确认环(ask),未确认不得执行,无确认通道时 SHALL fail-closed 拒绝。抓取失败 SHALL 返回包含 URL 与原因的明确错误,不抛未捕获异常。

#### Scenario: 抓取成功返回治理文本

- **WHEN** 以 http/https URL 调用 `web_fetch`
- **THEN** 返回页面文本,结构化元数据包含 url、来源与完整性(complete/truncated)

#### Scenario: 非 http/https scheme 拒绝

- **WHEN** 传入 `file://` 或其它非 http/https URL
- **THEN** 返回明确错误且不发起任何抓取

#### Scenario: 大响应有界截断

- **WHEN** 响应内容超过输出上限
- **THEN** 返回受限文本并标记 truncated,元数据保留原始总量与展示量

#### Scenario: 网络出站需确认

- **WHEN** 安全分类器判定 `web_fetch` 调用
- **THEN** 结论为 ask;未确认不执行;无确认通道(headless)时 fail-closed 拒绝

### Requirement: web_search 网页搜索

`web_search` 工具 SHALL 经注入的搜索提供方执行检索并返回有界的结果列表(编号展示,条数支持 limit、缺省 5);未注入搜索提供方时 SHALL 返回明确的不可用提示并指引改用 `web_fetch`,不得伪造搜索能力。搜索失败 SHALL 返回包含查询与原因的明确错误;无匹配 SHALL 明确报告。网络出站调用 SHALL 进入确认环(ask),无确认通道时 SHALL fail-closed 拒绝。

#### Scenario: 未注入提供方返回不可用

- **WHEN** 组合根未注入搜索提供方而调用 `web_search`
- **THEN** 返回不可用提示并指引使用 `web_fetch`,不注册或伪造搜索结果

#### Scenario: 注入提供方返回编号结果

- **WHEN** 注入搜索提供方并以 limit=2 检索
- **THEN** 返回至多 2 条编号结果行,输出遵守统一上限治理

#### Scenario: 无匹配明确报告

- **WHEN** 提供方返回空结果
- **THEN** 返回「无匹配结果」的明确报告

### Requirement: todo 任务清单

`todo` 工具 SHALL 以整体替换语义维护会话级任务清单:一次提交完整清单(条目含稳定 id、描述、pending/in_progress/done 三态),整体替换当前状态,空清单 = 清空;状态可由单次调用重建,幂等且无增量失同步。条目数 SHALL 有上限、id SHALL 唯一、字段 SHALL 非空,违规 SHALL 返回明确错误且不改变现有状态。任务清单 SHALL 仅驻内存,不进入会话持久化格式;状态 SHALL 可经注入的 `TodoState` 观察。

#### Scenario: 整体替换清单

- **WHEN** 提交包含若干条目的完整清单
- **THEN** 当前状态被整体替换为该清单,返回带状态标记的最新清单

#### Scenario: 空清单清空

- **WHEN** 提交空清单
- **THEN** 当前状态被清空并返回「任务清单为空」

#### Scenario: 非法清单拒绝且状态不变

- **WHEN** 清单含重复 id 或条目数超上限
- **THEN** 返回明确错误,现有清单状态保持不变

## MODIFIED Requirements

### Requirement: 工具注册与装配

系统 SHALL 通过 `make_tools` 工厂装配十一个原子工具,名称固定为 `read`、`write`、`edit`、`bash`、`grep`、`find`、`ls`、`skill`、`web_fetch`、`web_search`、`todo`。每个工具 SHALL 对外暴露稳定的名称、描述与输入参数 schema,供编排层绑定;`skill` 工具 SHALL 在装配时注入技能注册表(组合根提供),不读取配置、不跨层;工具 SHALL 同时提供只读的运行环境能力快照供诊断和后续能力选择使用;MCP 工具 SHALL 经组合根加载后追加到工具列表(内建工具恒保留),命名含 `mcp__<server>__<tool>` 前缀。

#### Scenario: 工厂产出全部工具

- **WHEN** 调用 `make_tools` 装配工具集
- **THEN** 返回的工具列表中包含全部十一个名称:read、write、edit、bash、grep、find、ls、skill、web_fetch、web_search、todo

#### Scenario: 装配时注入工作目录

- **WHEN** `make_tools` 收到的配置含 `cwd`
- **THEN** 全部工具都以该 `cwd` 为相对路径解析基准
