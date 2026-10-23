# web/todo 工具补齐

## Why

技能适配器显式声明 `"web": False, "todo": False` 并向模型降级提示"当前不可用"(`app/skills/runtime.py`),但注册表数据化后新增工具只需追加声明即可扩展;生态实践(harness 类项目)表明 web 抓取/搜索与任务清单是技能工作流的基础依赖,缺失会迫使技能退化为"写 TODO 文件"的降级路径。同时能力声明为手工维护的静态字典,与实际工具集存在失同步风险。

## What Changes

- 新增 `web_fetch` 工具:http/https URL 抓取,网络经注入的 fetcher(缺省 urllib),响应读取有界,输出按统一上限治理并携带完整性事实。
- 新增 `web_search` 工具:经注入的搜索提供方检索;未注入时返回明确不可用提示(不伪造搜索能力),与 `skill` 工具"未注入"语义一致。
- 新增 `todo` 工具:整体替换语义的会话级任务清单(pending/in_progress/done 三态),状态经 `TodoState` 注入可观察,仅驻内存不进入持久化格式。
- 工具注册表(`BUILTIN_TOOL_SPECS`)注册三个新工具,内建工具集由八个扩展为十一个。
- 安全分类:web 工具(网络出站)进 ask 档,headless 无确认通道时 fail-closed;todo 直接放行。
- 技能适配器能力声明(web/todo/subagents 等)改为从工具注册表自动派生,消除手工失同步。

## Capabilities

### New Capabilities

### Modified Capabilities

- `tools`: 新增 `web_fetch` / `web_search` / `todo` 三个工具需求,内建工具集扩展为十一个,网络出站进入确认环。

## Impact

- 影响 `src/codeagent/tools/atomic/`(新增 3 个工具模块)、`tools/registry.py`、`tools/security/classifier.py`、`app/skills/runtime.py`。
- 不改动既有八工具行为、会话持久化格式、provider 协议和事件类型集合;`todo` 清单不落盘。
- 测试全部离线:web 工具注入假 fetcher/searcher,不发起真实网络请求。
