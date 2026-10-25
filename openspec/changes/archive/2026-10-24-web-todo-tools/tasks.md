# Tasks

- [x] 1.1 `tools/atomic/web_fetch.py`:http/https 校验、注入式 fetcher(缺省 urllib、读取有界)、govern_text 输出治理
- [x] 1.2 `tools/atomic/web_search.py`:注入式 searcher,未注入返回不可用提示;limit 缺省 5,结果编号并治理
- [x] 1.3 `tools/atomic/todo.py`:整体替换语义、三态条目、`TodoState` 注入、id 唯一与条目上限校验
- [x] 2.1 `tools/registry.py`:`BUILTIN_TOOL_SPECS` 注册 web_fetch / web_search / todo(顺序契约更新)
- [x] 2.2 `tools/security/classifier.py`:web 工具 ask 档(headless fail-closed);todo 放行
- [x] 2.3 `app/skills/runtime.py`:能力声明与工具映射从工具注册表自动派生
- [x] 3.1 测试:工具行为(假 fetcher/searcher 离线)、分类、注册契约、能力派生
- [x] 3.2 更新 `openspec/specs/tools/spec.md` 与 wiki 工具清单
