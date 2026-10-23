# core Specification 变更

## MODIFIED Requirements

### Requirement: 工具执行确认

Agent Runtime SHALL 在每个工具调用执行前执行有序的 `before_tool_calls` 钩子链;每个钩子可以通知(返回 None,继续链)、改参(返回修改后的 ToolCall,后续钩子与执行只见新 call)、放行并附带警告(允许决策携带 warning)或阻止执行并提供原因(短路)。链 SHALL 按注册顺序执行,阻止短路后不执行工具、不执行后续 pre 钩子、不执行 post 链,该调用 SHALL 以错误结果回填且不得产生工具副作用。core SHALL 不读取安全配置、不实现具体审批策略;上层安全策略门禁 SHALL 位于链尾并对改参后的调用做判定。

#### Scenario: 允许执行

- **WHEN** pre 链全部返回通知或允许
- **THEN** 工具正常执行,结果照常回填 Agent 上下文

#### Scenario: 扩展阻止执行

- **WHEN** 任一 pre 钩子返回阻止及原因
- **THEN** 工具不得执行,后续 pre 钩子与 post 链不运行,该调用以失败结果回填并携带阻止原因

#### Scenario: 扩展改参

- **WHEN** pre 钩子返回修改后的 ToolCall
- **THEN** 后续 pre 钩子、策略门禁、确认事件与工具执行都只见修改后的参数

#### Scenario: 警告累积

- **WHEN** 多个 pre 钩子以允许决策携带警告放行
- **THEN** 警告按链顺序累积,并以单一安全提示前缀附着到工具结果供模型可见

#### Scenario: 需确认后批准

- **WHEN** 上层确认适配器将需要确认的调用判定为允许
- **THEN** core 收到允许决策并执行工具,结果照常回填

#### Scenario: 需确认后拒绝

- **WHEN** 上层确认适配器将需要确认的调用判定为拒绝
- **THEN** core 收到阻止决策,工具不执行,调用以失败结果回填并携带拒绝原因

#### Scenario: 策略拒绝

- **WHEN** 上层安全策略在链尾门禁阶段直接阻止调用
- **THEN** 工具不执行,调用以失败结果回填并携带策略原因

#### Scenario: 交互确认由上层完成

- **WHEN** 扩展需要用户确认才能决定是否执行
- **THEN** session/app 层负责等待用户响应并向 hook 提供最终决策,core 不直接依赖确认队列或 TUI/headless 配置

### Requirement: Agent Runtime 扩展钩子

Agent Runtime SHALL 只通过 provider-neutral 的配置协议接收 ContextTransformer、预算感知上下文扩展、有序工具 Hook 链和生命周期 Hook;core 不得发现、实例化或导入任何具体 provider、工具、MCP、Skill、memory 或 UI 实现。应用组合根负责把具体实现归一并注入运行配置,运行时只执行已注入的协议对象,且不因 session 恢复、模型切换或 TUI 重建而改变其顺序和语义。pre 链 SHALL 顺序执行并传播改参;post 链 SHALL 顺序执行,每钩子返回 None 保留当前结果、返回 ToolResult 则替换并传给下一钩子。其余上下文转换、工具 Hook 异常、超时、取消和回滚规则保持既有契约。

#### Scenario: 上下文扩展

- **WHEN** 注册了 `transform_context` 扩展
- **THEN** 每次模型请求前扩展可以基于当前消息副本生成模型可见上下文,而不修改 session 持久化的原始消息

#### Scenario: 预算感知上下文扩展

- **WHEN** 注册了需要预算信息的上下文扩展
- **THEN** 扩展收到中立的请求预算视图并可以生成当前请求的临时上下文,不得要求 core 直接提供 provider、session、MCP 或 Skill 具体实现

#### Scenario: 扩展只执行注入对象

- **WHEN** Agent 收到由应用组合根注入的运行时扩展集合
- **THEN** core 只调用集合中的协议对象,不自行发现或实例化任何具体扩展实现

#### Scenario: 上下文扩展超时或非法返回

- **WHEN** 上下文扩展超过配置时限或返回不是有效消息集合
- **THEN** Agent 产生带扩展阶段、错误码和原因的上下文准备错误,且不调用模型

#### Scenario: 上下文扩展取消

- **WHEN** 运行在等待上下文扩展时被取消
- **THEN** 取消向上传播,扩展不会被包装成普通错误,且不会留下悬挂的模型请求

#### Scenario: 工具前置拦截

- **WHEN** `before_tool_calls` 链中任一扩展阻止某个调用
- **THEN** 该调用不执行并生成结构化错误结果,同批其它调用按正常策略处理

#### Scenario: 工具结果后处理

- **WHEN** `after_tool_calls` 链中扩展修改工具结果或声明终止后续模型请求
- **THEN** Agent 使用链尾结果完成当前 turn,并按终止决策决定是否继续下一次模型请求

#### Scenario: 扩展异常

- **WHEN** 上下文或工具扩展抛出异常
- **THEN** Agent 发出带错误类型和阶段信息的错误事件,调用方可以回滚本轮且不得静默继续执行

#### Scenario: 预算计算失败
