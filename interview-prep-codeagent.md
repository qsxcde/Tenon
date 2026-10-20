# CodeAgent 面试准备手册

> 面向：把这个仓库写进简历后，被追问「架构 / 编排 / 会话 / 工具安全 / 上下文 / 质量」六大块时的应答准备。
> 口径来源：本仓库当前工作树（v0.5.0，`0fec298` + 未提交改动）。所有数字都在 2026-10-20 用本机 Python 3.12.13 实测过，附复现命令。
> 本地准备材料，不要提交进仓库。

---

## 0. 怎么用这份材料

三层准备，按时间投入排序：

| 层级 | 内容 | 目标 |
|---|---|---|
| **必须能脱口而出** | §1 三档自我介绍、§2 数字弹药库 | 开场 30 秒不虚，被问数字能立刻报出且可复现 |
| **必须能讲 2 分钟** | §3–§9 每条主线的「★」标记问题（约 20 个） | 覆盖 80% 实际提问 |
| **防守用** | §11 已知软肋 + 诚实回答模板 | 面试官真读了代码时不当场崩 |

一条总原则：**这个项目的卖点不是"我做了个 Agent"，而是"我把一个会失控的东西（模型输出、工具副作用、上下文膨胀、持久化崩溃）变成了可验证的工程边界"。** 所有回答都往这个方向收。

---

## 1. 三档自我介绍

### 30 秒版（自我介绍环节）

> 我写了一个本地优先的命令行编程 Agent，叫 CodeAgent，从零实现、约 3 万行 Python。
> 核心是自研的 ReAct 编排引擎，不用 LangChain/LangGraph，用端口-适配器分层：核心层是纯内存可测试的，模型、工具、存储全部通过协议注入。
> 配套做了 JSONL 会话持久化与崩溃恢复、请求级上下文预算与自动压缩、危险命令三档安全判定，以及 1700 个全离线测试和四层 CI 门禁。

### 2 分钟版（项目深挖开场）

在 30 秒基础上加三段，每段一句"难点 + 我的解法 + 可验证证据"：

1. **编排**：不用框架的代价是要自己处理多工具并发、取消合成、流式时序。我把"无状态主循环"和"有状态 Agent"拆开，循环只在上下文副本上跑，成功才提交——这给会话层一个干净的回滚边界。
2. **上下文**：长对话必然溢出。我做了请求级预算 preflight（safe / near_limit / over_limit / uncertain 四态），超限前先做确定性工具结果裁剪，再不行才触发压缩（0.8 触发、0.65 回收），压缩失败有冷却防止每轮重试。
3. **质量**：1711 个测试全部离线可跑（fake provider，零网络零密钥），单次全量 36 秒；mypy 分层棘轮把类型债务从 1060 降到 22；还有架构解耦的 AST 契约测试和文件规模门禁。

### 8 分钟版（如果让你画架构图）

按数据流讲，不要按目录讲：

```
用户输入 → TaskSupervisor(模式: ask/plan/code)
        → AgentSession(会话壳: 历史/预算/压缩/持久化)
        → Agent(有状态门面) → run_agent_loop(无状态主循环)
             ├─ prepare_context: 预算估算 → preflight → 工具结果裁剪
             ├─ model.stream: SSE → text_delta / thinking_delta / tool_call
             └─ execute_tool_batch: 并发 + 保序 + 取消合成
                  └─ ToolExecutionRuntime(信号量/超时/清理) → 8 个 AtomicTool / MCP / delegate
        → 事件流(40 类) → EventBus → TUI(30fps 渲染协调) / Headless / 测试
        → 成功才 commit_turn → JSONL 追加 + fsync + 索引
```

---

## 2. 数字弹药库

> 规则：**只报你能当场跑出来的数字**。下表全部实测于 2026-10-20，macOS / Python 3.12.13 / pytest 9.1.1 / mypy 2.4.0。

| 指标 | README/简历口径 | 实测 | 复现命令 |
|---|---|---|---|
| 全量离线测试 | 1711 passed | ✅ **1711 passed，36s（collect 0.8s）** | `.venv/bin/python -m pytest -q` |
| 快速质量集 | 1562 passed | ✅ **1562 passed**，24s（无 cov）/ 32s（带 cov） | `pytest -m "unit or contract" -q` |
| **覆盖率** | 86.35% | ⚠️ **86.35% 是快速集口径；全量口径是 90%**（18451 stmts / 1862 miss） | 加 `--cov=codeagent --cov-report=term` |
| mypy 分层债务 | session 5 / app 17 / 合计 22 | ✅ **core 0 / ai 0 / tools 0 / session 5 / app 17 = 22** | `scripts/type_scan.py` |
| 类型债务起点 | 1060 | ✅ **1060**；在旧提交上复跑得 **1049**（版本差异） | `git show 076c53a:docs/type-baseline.json` |
| 规模门禁 | ≤300 / ≤80 | ✅ 0 违规；最大文件**恰好 300**，最大函数**恰好 80** | `scripts/scale_scan.py` |
| OpenSpec | 24 份 | ✅ **24 passed, 0 failed** | `openspec validate --specs` |
| **生产代码行数** | 简历写"约 1.8 万行" | ❌ **物理 36176 / 非空 31193 / 纯代码 28757** | `find src -name "*.py" \| xargs cat \| wc -l` |
| 测试代码行数 | — | **28371** | `find tests -name "*.py" \| xargs cat \| wc -l` |
| 测试文件 / 函数 / 断言 | — | **140 文件 / 1297 个 test 函数 / 3832 处 assert**（仅 4 个测试无断言） | `grep -rn "def test_" tests \| wc -l` |
| 事件类型 | — | **40** | `rg -c '^    [A-Z_]+ = "' src/codeagent/core/contracts/events.py` |
| 工具数 | 8 内置 | **8 内置 + `delegate` = 9 个 AgentTool** | `ls src/codeagent/tools/atomic/` |
| marker 分布 | 9 个 | **unit 1041 / contract 521 / integration 114 / e2e 15 / platform 6 / security 39 / performance 20 / slow 20 / compatibility 26** | `pytest -m <marker> --collect-only -q \| tail -1` |
| 注解覆盖率 | — | **1794/1824 = 98.4%** 函数有完整注解 | 见 §11.12 脚本 |
| 分层行数 | 5 层 | core 5491 / session 8008 / ai 2001 / tools 4360 / app 16309（app 里 TUI 占 8922） | `for d in ...; do wc -l; done` |

### 三个必须能解释清楚的口径陷阱

**① 86.35% 和 90% 是两个不同的数。**

- `86.35%` = **快速集只有 1562 个测试**跑出来的（`18451-2519)/18451`），这是 CI 里 `--cov-fail-under=80` 保护的那个数。
- `90%` = **全量 1711 个测试**跑出来的（`18451-1862)/18451`）。
- README 把"1711 passed · 覆盖率 86.35%"并列书写，**容易被读成"1711 个测试跑出 86%"**。正确说法是："快速集 1562 个测试，覆盖率 86.35%；全量 1711 个测试，覆盖率 90%。"

**② 这些数字依赖未提交的工作区。**

当前工作区有 15 个修改 + 2 个未跟踪文件（含 `tests/conftest.py` 的 marker 优先级改动、`test_assembly.py` 拆分、CI 覆盖率下限 77.9→80）。**HEAD 上的数字是 1710 passed / 84.58% / 下限 77.9。** 如果面试官照 GitHub 上的 main 分支跑，会看到旧数字——**投递前先提交**，或者提前说明"我本地有未合并的改进"。

**③ 1060 的构成**：`15+14+24+311+696`。其中 `app` 的 696 里 **609 条是 `attr-defined`**，`session` 的 311 里 **270 条同样是 `attr-defined`**——这是 §9.5 的关键伏笔，也是"一次结构收敛"而非"逐条修 1000 个"的原因。

**④ 1711 的分布**：快速集 1562 + 跨边界集 149。但注意 `-m "integration or e2e or platform or compatibility"` 实际选中 **161** 个，因为**有 32 个测试同时带 unit/contract 与横切 marker，两个 job 都跑**；另有 **20 个测试（performance/slow）CI 完全不跑**。

---

## 3. 架构主线（★ = 高频）

### ★3.1 为什么分五层？core 为什么不能 import ai？

**答案骨架**：分层的判据不是"职责像不像"，而是**变更频率和失败模式是否不同**。

- `core/` 是纯内存编排：给定消息列表和模型端口，产出一批新消息。它没有网络、没有磁盘、没有密钥，所以**可以用假模型在毫秒级跑完整循环**。
- `ai/` 会变（供应商 API）、会失败（429/超时/SSE 断流）、会泄漏（密钥、连接）。
- `session/` 会变（存储格式、恢复策略）、会丢数据（崩溃在半行）。
- `tools/` 会变（工具集）、会搞坏机器（rm -rf）。

如果 core import 了 ai，那么"换一个 provider"或"provider 报错"就会穿透到编排层。现在的规则是：**core 只认识 `ModelPort` 这个 Protocol，谁实现它、怎么重试、密钥从哪来，core 不知道也不该知道。**

**追问：那 core 怎么处理 provider 错误？**
不处理，让它冒泡。core 只在异常时发一个 `ERROR` 事件（带 `error_type`；如果是 `ContextPreparationError` 还会带 `error_code/phase/cause_type`）然后 `raise`。分类和重试在 `ai/` 的传输层，中文映射在 `session/runtime/error_policy.py`，UI 展示在 TUI。见 [loop.py:59-64](src/codeagent/core/orchestration/loop.py#L59-L64)。

**别说**：不要说"为了解耦"就完了——那是同义反复。要说"为了把不可测的东西挤到边界外"。

---

### ★3.2 有几个端口？为什么 tools 不能 import core？

**答案骨架**：端口集中在 [ports.py](src/codeagent/core/contracts/ports.py)，核心就四个：`ModelPort`（模型）、`AgentTool`（工具）、`ToolExecutionRuntimePort`（受控执行）、`ApprovalPolicy`（安全决策），加上 `Summarizer`（压缩摘要）。

`tools/` 不 import `core/` 是个**反向约束**，容易被质疑"工具不需要知道 ToolResult 吗？"。答案是：工具层有自己的结果形态（`AtomicTool._invoke` 返回 `str` 或 `GovernedText`），跨层的形态转换**只发生在一个地方**——[app/composition/tools/adapter.py](src/codeagent/app/composition/tools/adapter.py) 的 `AgentToolAdapter`。这样：
- tools 层可以独立测试，不需要构造 core 的对象；
- core 换工具协议不会连带改 8 个工具；
- 旧式对象（带 `invoke`/`Args`）传进来会得到明确的"工具契约错误"，而不是偷偷走兼容路径（见 [agent-tool-migration.md](docs/design/agent-tool-migration.md)）。

**追问：这个约束怎么保证不被人绕过？**
[test_decoupling.py](tests/test_decoupling.py) 用 AST 扫全部 337 个源文件，每个文件按所在层匹配禁止前缀，345 个参数化用例。它连"规则写错导致扫了 0 个文件"都防了（`test_scan_has_content` 断言至少 60 个文件、每层都有）。

---

### ★3.3 依赖规则的具体漏洞是什么？（主动说，赢了）

**答案骨架**：我用测试里**真实的 helper**（`_imported_modules`）逐条验证过，六类绕过里有五类成立：

| 写法 | 是否被抓到 | 说明 |
|---|---|---|
| `from ..ai import x`（相对导入跨层） | ❌ 漏 | `_imported_modules` 丢弃 `level > 0` |
| `from codeagent import ai` | ⚠️ 半漏 | 只记录到 `codeagent`，不展开到 `ai` |
| `from codeagent.app.config import Settings` | ❌ 漏 | **禁的是 `codeagent.config`，这个模块根本不存在**（空转禁令）；且 `core` 的禁列表里**没有 `codeagent.app`** |
| `importlib.import_module("codeagent.ai")` | ❌ 漏 | 只看到 `importlib` |
| `__import__("codeagent.ai")` | ❌ 漏 | 记录为空 |
| `if TYPE_CHECKING: from codeagent.ai import x` | ✅ 抓到 | `ast.walk` 不区分，属"过严"而非漏洞 |

**两个最关键的发现**：
1. **`codeagent.config` 这条禁令是空的**——规则写的是 `codeagent.config`，而实际模块是 `codeagent.app.config`，所以**这条规则从未生效过**。
2. **`core → app` 完全没禁**。`_forbidden_for("core/...")` 返回 `["codeagent.config", "codeagent.tools", "codeagent.ai", "codeagent.session"]`，**没有 `codeagent.app`**。

**正面证据（要说）**：我另写了一个严格解析器（解析相对导入 + 展开 `from codeagent import X`）跑全树，**0 违规**；`scripts/layer_scan.py` 的跨层矩阵也是严格三角（core→{}、ai→{}、tools→{}、session→core 110、app→core 142/session 15/ai 15/tools 15）。**所以"今天代码是干净的"，但干净靠纪律，不靠规则完备。**

**改进顺序**：① 先把 `codeagent.config` 改成 `codeagent.app.config` 并给 core 加 `codeagent.app`；② 解析相对导入（`resolve_relative(path, level, module)`）；③ 展开 `from codeagent import X`；④ 把 `importlib`/`__import__` 的字面量参数也扫进去；⑤ 长期迁移到 import-linter 的 `layers` + `forbidden` 契约。

---

### 3.3b 架构门禁自身有个真 bug：1 个用例在 CI 永远不跑

**实测**：`tests/test_decoupling.py::test_layer_import_rules[app/tui/benchmark/performance.py]` 这个参数化用例，因为**参数 id 里含 "performance"**，被 `conftest.py` 的启发式规则打上了 `performance` + `slow` marker。结果：

```
-m "unit or contract"                                  → 1 deselected（不跑）
-m "integration or e2e or platform or compatibility"    → 1 deselected（不跑）
-m performance                                          → 1 test collected（但 CI 的 performance job 只跑 benchmark，不跑这个）
```

**所以"架构门禁覆盖 337 个文件"这句话，实际是 336 个。** 根因在 [conftest.py](tests/conftest.py) 的 `"performance" in name` 判断——它本意是抓 `test_performance_*`，但用的是 `item.name`（含参数化 id）。

**修法**：判断改成 `name.startswith("test_performance")` 或 `path.endswith("test_performance.py")`，不要对 `item.name` 做子串匹配。

**这个故事的价值**：它证明"门禁本身也需要测试"，而我的门禁缺这一层。同类的 `tests/tui/test_fuzzy.py::test_performance_within_budget` 也被误标，一个普通单测被踢出快速集。

---

### 3.4 `AgentLoopConfig` 是"唯一窗口"是什么意思？

**答案骨架**：编排层认识外部世界的**全部**信息都在这一个 dataclass 里：`model`、`tools`、`tool_runtime`、`transform_context`、`context_preparer`、`context_budget`、`context_preflight`、`before_tool_call`、`after_tool_call`、`lifecycle_hooks`、`tool_execution`、`steer_queue`、`context_window/output_reserve/reserve_tokens`。

好处是**依赖注入变成一次性的**：想让 core 做新事，要么加字段（显式扩展点），要么它就不该做。坏处是 dataclass 会膨胀——现在有 20+ 字段，这也是为什么 `SessionExecutionMixin._build_agent_config` 要用 `dataclasses.fields()` 反射复制（[execution.py:100](src/codeagent/session/runtime/execution.py#L100) 附近），这个写法本身有点脆：**加字段忘了在 `__post_init__` 校验就会静默通过**。

**追问：为什么不拆成多个 config？**
因为拆了之后每个组合根都要传 5 个对象，且"某个组合漏传一个"的错误在运行时才暴露。现在是"一个对象 + `__post_init__` 集中校验"（例如 `uncertain_budget_policy` 必须是 allow/fail，`context_transform_timeout` 必须有限正数）。

---

### 3.5 为什么组合根拆成 `composition/*` 而不是一个 `container.py`？

**答案骨架**：最初就是一个 `container.py`（约 800 行），触发拆分的不是审美而是**规模门禁**（单文件 ≤300 行）。拆的时候按"被装配的东西"分：`model/`（客户端+预算+能力探测）、`tools/`（工厂+定义+适配）、`session/`（session/manager 工厂）、`runtime/`（AgentLoopConfig 组装+扩展）、`subagent/`（子代理装配）、`tui/`（TUI 装配）。

`container.py` 降级成 façade，只做 re-export。并且用测试禁止 composition 反向 import façade（否则循环依赖）。

**追问：这是不是为了过门禁而拆？**
部分是。但拆完有个真实收益：`app/composition/policy.py` 这种纯策略文件可以单独测。这次把 `test_assembly.py` 里唯一启动 MCP 子进程的用例拆出去并标 `integration` 之后，`policy.py` 的快速集覆盖率从 20% 涨到 84%——**deny / interactive / allow 三条安全分支从此每次 CI 都跑**。这是个"门禁倒逼出的真实收益"的好故事。

---

### 3.6 双层 loop 指什么？

**答案骨架**：**外层是轮（turn）循环，内层是一次模型的流式装配。**

- 外层：[loop.py](src/codeagent/core/orchestration/loop.py) 的 `for iteration in range(recursion_limit)`，每轮调 `run_turn`。
- 一层轮内：[turn.py](src/codeagent/core/orchestration/turn.py) 的 `run_turn`：发 `TURN_START` → 拿一条完整 assistant 消息 → 无 tool_calls 就结束 → 有就执行整批工具 → 回填 tool 消息 → 处理 steer → 发 `TURN_END`。
- 再往里：[request.py](src/codeagent/core/model/request.py) 的 `new_model_message` 负责"一次模型请求"：预算 → preflight → 流式消费 → 组装 tool_calls。

**为什么值得这么分**：三层各自有独立的失败语义。模型请求失败 = 可重试的传输问题；轮失败 = 循环该终止；工具批失败 = 可以降级成"部分成功 + 错误结果回填给模型"。混在一起就没法分别处理。

---

### ★3.7 事件驱动：40 个事件类型会不会太多？订阅方异常会不会拖垮主流程？

**答案骨架**：事件多是因为**工具生命周期本身就是多态的**（queued → start → update → end，外加 cancelled / timed_out / rejected / truncated 各种终态），不是为了好看。

关键设计是**观察者隔离**（[agent.py:96-113](src/codeagent/core/agent.py#L96-L113)）：

```python
for listener in tuple(self._listeners):
    try:
        result = listener(event)
    except Exception as exc:
        self._listener_errors.append((event, exc))   # 收集，不上抛
        continue
    if inspect.isawaitable(result):
        task = asyncio.create_task(self._consume_listener(result, event))
        self._listener_tasks.add(task)               # 登记，退出时统一收割
```

同步异常直接吞进 `listener_errors`；异步异常进 `_consume_listener` 同样收集。**订阅方挂了，会话不知道，但也不会挂。**

而且在 `_execute` 的 `finally` 里会 drain 所有监听任务：正常结束 `gather` 等待（保证终态事件可观测），取消时先 `cancel` 再 `gather`。

**追问：那每来一个 delta 就 `create_task`，不会炸吗？**
会——这正是我在评审里发现的问题（`_emit` 在每次流式增量时调用）。修复方式是任务登记 + 退出收割，但**每个 delta 一个 task 的开销还在**。诚实答案：目前靠 TUI 侧的 30fps 事件缓冲把下游压力削掉了，但 core 侧的 task 数仍随 delta 线性增长；更好的做法是 core 只对**可 await 的监听器**建 task，同步监听器直接调。

---

## 4. 编排主线

### ★4.1 ReAct 循环的终止条件是什么？

**答案骨架**：三条路径：

1. **自然结束**：模型返回的 assistant 消息 `tool_calls` 为空 → `run_turn` 返回 `True` → 循环 break。
2. **达到上限**：`recursion_limit`（默认 50）耗尽 → 抛 `RecursionLimitError`。注意**最后一轮如果还要调工具，会先抛错**（`turn.py` 里 `if is_last: raise RecursionLimitError()`），不是静默截断。
3. **外部终止**：`abort()` → `task.cancel()` → `CancelledError` → 发 `ABORTED` 事件（带 cleanup 状态）→ 重新 `raise`。

另外还有一个**扩展终止点**：`should_stop_after_turn` 回调，每轮工具执行完问一次"要不要停"，用于 `TaskSupervisor` 这类"验证通过就停"的策略。

**追问：50 这个数字是什么语义？**
是**轮数**（模型调用次数），不是工具调用数。一轮可以并发 10 个工具。所以最坏情况 50 轮 × N 工具。这也是为什么工具侧还要有独立的并发上限和单次超时。

---

### ★4.2 多工具并发怎么实现？"保序"和"取消合成"分别指什么？

**答案骨架**：看 [batch.py](src/codeagent/core/orchestration/batch.py)。

- **并发**：`tool_execution == "parallel"` 时对每个 call `create_task`，用 `asyncio.as_completed` 消费。**默认就是 parallel**（`AgentLoopConfig.tool_execution = "parallel"`）。
- **真正的并发限制在下一层**：[ToolExecutionRuntime](src/codeagent/core/execution/runtime.py#L36) 里的 `asyncio.Semaphore(max_concurrency=4)`。所以"并发发起 10 个、同时最多跑 4 个"。
- **保序**：结果写回 `results[index]`，而 `index` 是模型给出的原始顺序。所以**完成顺序是乱的，但回填给模型的消息顺序严格等于模型请求的顺序**。这很重要——OpenAI 协议里 tool 消息按 `tool_call_id` 归属，顺序错了模型会困惑。
- **取消合成**：被 cancel 时，还没跑完的 task 全部 `cancel()` + `gather(return_exceptions=True)`，然后**给每个还没发过 `TOOL_EXECUTION_END` 的 call 补一条合成的 `CANCELLED` 结果**：

```python
_cancelled_result(call, operation_ids[index], config,
                  cleanup_required=index in started_indices)
```

`cleanup_required` 区分"排队中就被取消"（没启动，无需清理）和"跑到一半被取消"（要检查清理是否确认）。这让 UI 上不会出现"永远转圈的 tool block"。

**追问：一个工具抛异常会不会中断整批？**
不会。`new_tool_result` 里 `except Exception` 把工具异常转成 `ToolResult(error=True)` 回填给模型（[tool_call.py:47-58](src/codeagent/core/orchestration/tool_call.py#L47-L58)）。**只有 CancelledError 往上走**。这是有意设计：模型看到"工具执行出错: xxx"会自己换策略，比整个 run 崩掉好。

---

### ★4.3 steer / followup / abort 三者的区别和时序

**答案骨架**：

| 操作 | 语义 | 时序点 |
|---|---|---|
| `abort()` | 取消当前 run | 立刻 `task.cancel()` |
| `steer(text)` | 运行中注入一条用户消息 | **当前工具批执行完之后**、下一次模型请求之前（`_append_steering_messages`） |
| `followup(text)` | 本轮结束后再跑一轮 | 当前 run 的 `_execute` 循环里，`while self._follow_ups:` |

steer 的语义细节很关键：它**不是**插队打断模型，而是"这轮工具跑完、模型下一步决策前，让它知道用户改主意了"。源码注释写得很明确。

**追问：为什么 steer 要等工具批结束？**
因为如果工具批跑到一半改上下文，已经发出去的 tool_call 就没有对应的 tool_result，消息序列非法（OpenAI 协议要求每个 tool_call 都有回填）。这是一个**被协议倒逼的时序约束**，不是设计选择。

**追问：abort 之后 steer 队列会怎样？**
会被清空（`finally` 里 `self._steer_messages.clear()`），注释写着 "A cancelled run must not leak steering input into a later run"。这是真实的 bug 修复——早期版本取消后残留的 steer 会污染下一次 run。

---

### ★4.4 SSE 解析处理了哪些边界？

**答案骨架**：两层——[sse.py](src/codeagent/ai/transport/sse.py) 解析单帧 JSON，[streaming.py:110-153](src/codeagent/ai/transport/streaming.py#L110-L153) 处理帧边界。

处理的边界：
1. **分包**：`aiter_lines()` 按行读，一个 `data:` 可能多行。
2. **多行 data 合并**：非 `data:` 开头的空行视为帧结束，把 buffer 用 `\n` join 后解析。
3. **`[DONE]`**：先 flush 剩余 buffer 再 return。
4. **非法 JSON**：`SSEParser.feed` 里 `except json.JSONDecodeError: return []`——**静默丢弃**。这是有意的容错（有些 provider 会发心跳/注释帧），代价是"真的解析失败也看不出来"。
5. **空帧 / 纯空白**：返回空列表。
6. **tool_call 参数跨帧拼接**：按 `index` 累积到 `self._tool_args[index]`，`name` 和 `id` 可能只在首帧出现（后续帧 `name` 是空串），所以有 `if name:` 才覆盖。
7. **usage 独立帧**：`payload.get("usage")` 在任何帧里出现都会先发一个 `usage` 事件（有些 provider 把 usage 放在最后一个 choice 为空的帧里，所以 `if not choices: return events` 之前就处理了）。
8. **thinking**：读 `delta.reasoning_content`（DeepSeek/GLM 系的字段名），转成 `thinking` 事件。

**追问：`finish_reason == "length"` 怎么办？**
在 `parse_tool_arguments` 里，如果工具参数 JSON 解析失败且 `finish_reason == "length"`，错误信息会附上"(可能因响应截断)"（[port.py:107](src/codeagent/app/composition/model/port.py#L107) 附近）。这样模型下一轮看到的是可诊断的错误，而不是一句干巴巴的 "JSON 无效"。

---

### ★4.5 流式重试策略：什么时候能重试，什么时候不能？

**答案骨架**：一行关键变量 `yielded`（[streaming.py:89-105](src/codeagent/ai/transport/streaming.py#L89-L105)）：

```python
yielded = False
for attempt in range(self._max_retries + 1):
    try:
        async for event in self._stream_attempt(body, parser):
            yielded = True
            yield event
        return
    except Exception as exc:
        if yielded or not classified.retryable or attempt == max_retries:
            raise classified from exc
        await asyncio.sleep(retry_delay(attempt, retry_after=...))
```

**规则：一旦吐出过任何一个事件（哪怕只是一个字符），就永不重放。** 因为重放会造成文本重复，而用户已经看到了。

退避：解析 `Retry-After`（上限 10s），否则指数退避 `2^attempt` 也截到 10s。`max_retries` 硬上限 5。

**追问：那"首帧前失败"怎么定义？**
连接失败、HTTP 4xx/5xx（`resp.raise_for_status()` 在 yield 之前）、读流时的第一个事件之前断开。这三类都可以安全重试。

**追问：工具执行会不会被重试？**
不会，且这是有意的：`safe-model-retries` 的边界是"完整模型响应之前"。工具执行在传输层之外，重试模型不会重放工具副作用。

---

### ★4.6 六家 provider 怎么吸收差异？

**答案骨架**：**不是每家一个适配器，而是"一家的实现 + 六份配置"**。

- 传输层只有 [OpenAICompatClient](src/codeagent/ai/transport/openai_compat.py) 一个类（deepseek/openai/qwen/glm/kimi/minimax 全部 OpenAI 兼容）。
- 每 provider 一个自包含文件（如 [deepseek.py](src/codeagent/ai/providers/deepseek.py)，64 行）：一个 `BaseSettings` 配置类（`env_prefix="DEEPSEEK_"`、`extra="ignore"`）+ 一个 `make_llm()` 工厂。
- 差异被压缩到三个地方：**默认 base_url / 默认 model / `reasoning_effort` 是否透传**（只有 `ModelSpec.reasoning == True` 的模型才传）。
- 模型元数据（上下文窗口、max_tokens、是否支持 tool_calling、别名）集中在 `ai/catalog/builtin.py` 静态目录，不依赖 `/models` 探测（因为 `/models` 只返回 id）。

**追问：`extra="ignore"` 为什么重要？**
因为六家的密钥全写在同一个 `~/.codeagent/.env` 里。如果 pydantic 默认 `extra="forbid"`，那么 `Settings` 读到 `DEEPSEEK_API_KEY` 就会炸。这是真踩过的坑，已补回归测试。

**追问：为什么不用各家官方 SDK？**
三个理由：① SDK 把 reasoning_content、usage 细节、错误码抹平了，而这些恰恰是我们要透传给 UI 的；② 六个 SDK 的依赖树会互相冲突；③ 自研 SSE 只有 ~60 行，比调试 SDK 的黑盒便宜。

---

### 4.7 死循环怎么防？（除了 recursion_limit）

**答案骨架**：`recursion_limit` 只能防"轮数爆炸"，防不了"同一轮里反复调同一个工具"。现在有的防线：

1. **模型访问上限**：50 轮硬停。
2. **工具并发上限 + 超时**：`Semaphore(4)` + `timeout`（默认 `tool_timeout` 可为 None，`max_timeout=600`）。
3. **subagent 双重预算**：`max_turns=8` / `max_tool_calls=32` / `timeout=120s`，硬上限 `16/64/300`。
4. **压缩冷却**：自动压缩失败后，同一个 fingerprint 不会每轮重试（`_last_compaction_failure_fingerprint`）。

**诚实补充**：**没有"重复调用检测"**。如果模型连续 20 轮调 `read` 同一个文件，循环会照跑到 50 轮。这是我认为最值得补的一环——可以用"最近 N 次工具调用的 (name, args_hash) 指纹去重"来做，命中就注入一条"你已经这样做过了"的系统提示。

---

## 5. 会话主线

### ★5.1 JSONL 记录格式长什么样？

**答案骨架**：**一行一条 JSON，按 `type` 字段多态**。7 种记录：

| type | 内容 | 何时写 |
|---|---|---|
| `session` | header：id / timestamp / cwd / parentSession / model / effort / version | 会话创建时（第一行） |
| `message` | role / content / tool_calls / tool_call_id / id / parentId | 每轮成功提交 |
| `usage` | input/output/reasoning/cached tokens | 每轮成功提交 |
| `meta` | key/value（`name` 会话标题、`archived` 归档、`last_context_tokens`） | 命名/归档/提交后 |
| `model_change` | model / effort | `/model` 切换 |
| `compaction` | id / parentId / summary / firstKeptEntryId / details | 压缩时 |
| `subagent` | 有界运行事实（状态/阶段/终态/清理） | 委派终态 |

**为什么是 JSONL 而不是 SQLite**：① 追加即持久，单条记录写入不需要事务；② 损坏是**局部的**——坏一行只丢一行，可以继续用其余历史；③ 人可读，出事能直接 `tail`；④ 会话是"只追加的日志"这个心智模型和 LLM 的 turn 语义天然对齐。

**代价（要主动说）**：查询必须全文件扫或维护索引；跨会话聚合查询很难；文件会无限增长（压缩只改逻辑视图，物理历史全保留）。

---

### ★5.2 "成功才落盘"具体是怎么实现的？

**答案骨架**：三层配合，**关键是"循环跑在副本上"**。

1. **core 层**：`run_agent_loop` 里 `working = context.copy()`，所有新消息都进 `working` 和 `new_messages`，**`context` 原对象一个字节都不动**（[loop.py:73-90](src/codeagent/core/orchestration/loop.py#L73-L90)）。所以"回滚"在 core 层是空操作。
2. **Agent 层**：`self._context.messages.extend(messages)` 只在 `run_once` 成功返回后执行（[agent.py:140-145](src/codeagent/core/agent.py#L140-L145)）。异常时什么都不加。
3. **Session 层**：`SessionRunCoordinator.run` 里，只有 runtime 正常返回后才 `_commit()`；任何异常路径调 `_rollback(before_ids)`——即"把 history 过滤回本轮开始前的 id 集合"。

```python
def _rollback(self, before_ids: set[str]) -> None:
    self._history = [m for m in self._history if m.id in before_ids]
```

**注意这句的语义**：它假设本轮消息是"追加"上去的，所以按 id 过滤等价于截断。**如果本轮修改了已有消息（比如改写 content），这个回滚不会还原。** 目前没有这样的路径，但这是个隐含假设。

---

### ★5.3 那"取消"是不是真的不落盘？（这条要小心，见 §11.3）

**答案骨架（标准版）**：是的，`CancelledError` 走 `_cancelled()` → `_rollback(before_ids)` → 发 `RUN_CANCELLED` 事件，`CommitStatus` 是 `ROLLED_BACK`（如果清理不确定则是 `UNCERTAIN`）。

**追加的诚实版**：但**取消可能发生在提交过程中**。`AsyncPersistenceBoundary.run` 会 `shield` 住写线程，取消时**先等写完成再抛 CancelledError**——这是为了让已经持锁的追加不要被半途抛弃。这时磁盘已经写了，而 `_history = kept_history` 那一行还没执行，于是内存回滚、磁盘有数据。这是真实存在的边界（见 §11.3），修法是"提交标记 + 恢复时按磁盘为准"或者"先置 committed 标志再写"。

---

### ★5.4 崩溃恢复的三态怎么判定？

**答案骨架**：`healthy` / `degraded` / `unavailable`，判据在 [recovery.py](src/codeagent/session/persistence/jsonl/recovery.py)。

- **unavailable**（不可激活，保留原文件）：文件不存在 / 是符号链接 / 读失败（OSError/UnicodeError）/ **第一行不是合法 header** / 完全没有 header / `session_id` 非法。这些是**结构性错误**，继续用会写坏数据。
- **degraded**（可继续）：header 正常，但存在下列任一诊断——`malformed_record`（某行不是 JSON）、`invalid_record`（不是对象）、`index_missing` / `index_stale`、`compaction_cut_missing`（压缩切点消息不存在）。
- **healthy**：以上都没有。

关键设计：**恢复是只读的**（`recovery_report` 不重写任何东西），坏行只跳过不修复。诊断是结构化的四元组 `(code, message, impact, action)`，`action` 直接告诉用户该干什么（"请先备份 JSONL，再继续使用有效历史"）。CLI 用退出码 2 表示不可恢复。

---

### ★5.5 索引是怎么设计和失效的？（这条是软肋，见 §11.2）

**答案骨架（设计意图）**：每个会话旁边一个 `.<id>.index.json`，缓存 `session`（元数据）、`meta`（标题/首条用户消息）、`usage`（累计 token）、`lastCompaction`、以及 **`source` 指纹** `{size, mtime_ns, ctime_ns}`。读的时候先比指纹，匹配就直接用索引（O(1)），不匹配就全文件重建。

**为什么用三元组而不是只用 mtime**：某些文件系统（网络盘、粗粒度时间戳）的 mtime 精度不够，同一秒内的两次写入 mtime 相同但 size 不同；加入 `ctime_ns` 是为了捕捉"chmod 元数据变更但内容不变"。

**诚实补充**：实现上有一个顺序问题——`_append()` 是"先写文件、再读索引"，而索引的指纹是"上一次写完之后"的，所以**每次 append 读到的索引必然失效，走全量重建**（`apply_record` 增量分支实际走不到）。我实测 1500 次 append = 1500 次全量重建、6 秒，复杂度是 O(n²)。正确顺序是"写之前读索引 → `apply_record` 追加上去 → 写文件 → 用新指纹写索引"。

---

### ★5.6 文件锁：进程内和跨进程分别怎么做？

**答案骨架**：[locking.py](src/codeagent/session/persistence/locking.py) 的 `PathLock` 是**双层锁**：

1. **线程层**：`threading.RLock`（可重入，因为索引更新会重入同一路径的锁）。
2. **进程层**：sidecar 文件 `.<name>.lock` + OS advisory lock（POSIX 用 `fcntl.flock`，Windows 用 `msvcrt.locking`），默认 30s 超时、20ms 重试。

**为什么需要两层**：单进程内多线程要可重入（RLock），跨进程要 OS 锁（flock 对同一进程的不同 fd 行为不一致）。早期版本只有进程内锁，评审时发现"两个 codeagent 进程同时 append 会交错写坏 JSONL"，才补了 sidecar。

**追问：锁文件残留怎么办？**
`flock` 是 advisory 且随 fd 关闭自动释放，**进程崩溃不会留下死锁**（文件残留在，但锁没了）。这是选 advisory file lock 而不是"创建锁文件存在即锁"的原因。

**追问：同进程另一个线程读的时候会被阻塞吗？**
会，而且是一个真实问题：`_iter_entries` 在 `with self._lock_for(path)` 内 `yield`，所以**读迭代期间一直持锁**，另一个线程的 append 会被阻塞。应该是"读进内存再释放锁"。这是待优化项。

---

### ★5.7 fork 的语义是什么？

**答案骨架**：`fork(session_id, target_message_id, new_session_id)`——从**某个 user 消息之前**切一个新的会话文件。

- **原会话零修改**（只读源文件）。
- 新文件有全新 header，`parentSession` 指向源会话。
- 复制"分叉点之前的所有消息"（保证新会话的历史和分叉点一致），消息 id / parentId 链**原样保留**——这样恢复时父子链仍然能对上。
- 分叉点必须是 `user` 消息（不能在 assistant 或 tool 消息上分叉，否则新会话会以"没有提问的回答"开头）。
- 如果源会话有压缩记录，还要处理"分叉点是否在压缩切点之后"。

**追问：为什么要"消息 id 原样保留"？**
因为 `parentId` 是链式结构，如果 fork 时重新生成 id，就必须重写所有 parentId；而且恢复时"按 id 定位压缩切点"（`firstKeptEntryId`）会失效。

---

### ★5.8 压缩：0.8 / 0.65 到底是什么？

**答案骨架**（[policy.py:20-22](src/codeagent/session/compaction/policy.py#L20-L22)）：

```python
trigger_ratio: float = 0.8      # 估算输入达到 input_budget 的 80% → 触发
target_ratio: float = 0.65      # 压缩后希望降到 input_budget 的 65%
trigger_headroom_tokens: int | None = 2_048   # 或者剩余空间 ≤2048 token 也触发
min_recent_turns: int = 1       # 至少保留最近 1 个完整轮
```

- `trigger_budget = ceil(input_budget * 0.8)`
- `target_budget = floor(input_budget * 0.65)`
- **两个条件取或**：`input_tokens >= trigger_budget` **或** `headroom <= 2048`。第二条是给"窗口很小"或"估算不准"兜底的。

**切点策略**（`plan_compaction`）：从最后一条 user 消息往前扫，按**完整轮**（user → assistant → tools）累加 token，直到超过 `target_budget` 就停。保证**只切在 user 边界**，不拆轮次。四种结果码：`ready` / `no_op`（全部装得下）/ `no_safe_boundary`（没有 user 消息）/ `oversized_turn`（最近一轮本身就超 target，不能压）。

**追问：为什么是 0.8/0.65 而不是 0.9/0.5？**
0.8 留 20% 缓冲吸收"估算误差 + 本轮新增工具结果"；0.65 是"压一次能撑若干轮"的经验值——压到 0.5 会丢太多，压到 0.75 会很快又触发。**诚实说：这两个数是经验值，没有做参数扫描实验**，这正好是可以主动提的改进方向（用一组固定长对话 fixture 做 sweep）。

---

### ★5.9 压缩会不会丢关键信息？怎么验证？

**答案骨架**：会，所以做了四件事：

1. **摘要提示词要求保留精确事实**：文件路径、函数名、错误消息原文不能改写（`Summarizer` 端口的 prompt 约束）。
2. **结构化 details**：`extract_file_ops` 从被压缩的历史里抽出 `readFiles` / `modifiedFiles`，作为结构化字段跟着 compaction 记录落盘，不依赖自然语言摘要。
3. **二次压缩增量合并**：第二次压缩会把上一次的 summary 作为 `prev_summary` 传进去要求"合并而不是覆盖"，形成摘要链。
4. **恢复回归测试**：`context-recovery-regression` 覆盖正常/接近上限/超预算/不确定窗口/压缩成功-跳过-失败-取消/工具结果治理/恢复/分叉/模型切换等场景，断言压缩前后的语义和父链。

**追问：怎么定量验证"没丢"？**
诚实答案：**目前只有回归测试，没有 LLM-as-judge 或人工标注的保真度评估**。如果要做，我会构造"压缩前问 A，压缩后必须还能答 A"的探针集，按信息类型（文件路径/错误信息/约束条件/用户偏好）分类统计保持率。

---

## 6. 工具与安全主线

### ★6.1 8 个工具的设计共性是什么？

**答案骨架**：`AtomicTool[ArgsT]` 泛型基类，三条不变量：

1. **无状态**：工具不持有会话/缓存状态。可注入的只有 `cwd`、`FsOps`、`ToolResourceLimits`。
2. **文件系统抽象缝**：所有 IO 走 `FsOps`（默认 `LocalFsOps`），所以可以注入内存实现做测试，或将来远程化。
3. **输入是 pydantic 模型**：`Args` 类由组合根转成 JSON Schema 喂给模型；参数校验失败在适配层就变成 `INVALID_ARGUMENTS` 状态，不会进到工具内部。

**追问：为什么 `_invoke` 返回 `str` 而不是结构化对象？**
因为模型只吃文本。但需要携带元数据时返回 `GovernedText(content, metadata)`——元数据（总行数、退出码、是否截断、变更摘要）会进 `ToolOutputMetadata`，供 UI 展示和后续裁剪用，**但不占模型的 token**。

---

### 6.2 grep/find 的 rg/fd 回退是怎么设计的？

**答案骨架**：**外部二进制只当加速器，不是依赖**。

- 启动时探测能力（`tools/capabilities.py`），记录 `rg` / `fd` 是否存在。
- 存在就走外部进程；不存在或执行失败（非零退出、超时、参数不兼容）就走**纯 Python 实现**。
- 两者的输出格式、截断策略、排序规则必须一致，否则"同一命令在两台机器结果不同"。

**追问：回退触发条件具体是什么？**
不是只判"二进制不存在"。还要处理：老版本 rg 不支持某个 flag（比如 `--json` 的字段差异）、Windows 上 rg 输出路径分隔符不同、超时。这些都有专门的集成测试。

**追问：为什么不直接全用 Python？**
大仓库上性能差一个数量级（rg 是并行 SIMD 实现）。这里的设计取向是"**功能正确性不依赖外部工具，性能可以依赖**"。

---

### ★6.3 安全判定顺序 deny > ask > allow 具体怎么走？

**答案骨架**：四步，顺序不可换（[classifier.py](src/codeagent/tools/security/classifier.py)）：

1. **DENY（硬拒绝）**：危险模式正则（`rm -rf /`、fork bomb、mkfs、`dd if=/dev/*`、`>/dev/sd*`）+ 结构递归分析（`_dangerous_intent`：`eval`、嵌套解释器 `-c`、`rm -rf` 命中 `/`/`~`/cwd、未闭合 `$(...)`）+ 敏感路径（`~/.ssh`、`.env`、`*.pem`、`id_rsa`）。
2. **ASK（需确认）**：约 20 条规则表——`git push`、`git reset --hard`、`git clean -f`、`sudo`、`chmod -R`、`rm -r`、`find -delete/-exec`、`dd of=/dev`、`base64 -d | sh`、`xargs`、写 `/etc` 等系统目录、`tee /etc/*`、`docker -v /`、`tar -x -C /`、`awk system()`、kill 类、`mv` 覆盖已存在文件、`curl|sh`。
3. **ALLOW（白名单）**：`ls`、`cat`、`grep`、`pwd`、`echo`、`head`、`tail`、`which`、`git status/diff/log/show`。
4. **默认 ALLOW**（注意：不是 deny）。

然后**由 approval_mode 收口**：`deny`（headless 默认）把 ASK 降成 DENY；`allow`（`--yes`）把 ASK 升成 ALLOW；`interactive`（TUI 默认）真的发 `CONFIRMATION_REQUESTED` 等用户按 y/n。

**追问：为什么不默认 deny？**
如果默认 deny，那么所有"没预料到的命令"都要用户确认，Agent 基本没法干活。这里选的是"已知危险拒、已知敏感问、其余放行 + 工作区文件边界"。**这是产品取舍，不是安全模型**——要能明确说出这句话。

---

### ★6.4 文件访问边界怎么判？符号链接能逃逸吗？

**答案骨架**：`within_workspace()` 用**两级判定**（[filesystem.py:33](src/codeagent/tools/security/filesystem.py#L33)）：

1. **realpath 前缀匹配**：`Path.resolve()` 后比较 `normcase` 字符串前缀。
2. **inode 级兜底**：目标存在时，从 `realpath` 开始沿祖先链上溯，用 `os.path.samefile` 判断是否等于 workspace 根。这是为了处理**大小写不敏感文件系统**（macOS/Windows）和**硬链接**——字符串前缀会被 `Workspace`/`workspace` 骗过去，samefile 不会。

超界后的策略：**读越界放行 + 警告**（`warning=True`，模型能看到"越界读取"提示）；**写/编辑越界 → ASK**；**解析失败 → ASK**（保守）。

**我实测的符号链接场景**：workspace 内建一个指向外部的 symlink，往 `link/pwn.txt` 写 → 判定 `ask`（因为 `resolve()` 之后已经在外部）。**这是对的**。

**追问：TOCTOU 呢？**
存在。判定时 resolve，执行时再打开——中间被人换成 symlink 就能绕。真要防得用 `openat` + `O_NOFOLLOW` 逐段打开。**诚实答案：当前是"防误操作"级别，不是"防对抗"级别。**

---

### ★6.5 无头模式 fail closed 在哪实现？

**答案骨架**：三处配合。

1. [main.py:98](src/codeagent/app/main.py#L98)：`approval_mode="allow" if args.yes else "deny"`。
2. [policy.py](src/codeagent/app/composition/policy.py)：`decide()` 里 `if decision.action == "ask" and approval_mode == "deny": return PolicyDecision("deny", "未确认不得执行(headless): ...")`。
3. 结果回填给模型的是 `[工具执行被拒绝] <原因>`，`status=REJECTED`。

**关键点**：拒绝是**回填给模型继续**的，不是终止 run。所以 headless 模式下模型会知道"这个命令被拒了"，可以换个做法。这也是为什么 CLI 上能跑完而不是直接退出。

---

### ★6.6 bash 子进程怎么管：超时、清理、跨平台

**答案骨架**：

- **超时**：`asyncio.wait_for` 包住执行；超时后先 `_cleanup_operation()` 再返回 `TIMED_OUT` 结果，文案区分"已清理"和"停止等待但后台清理未确认"。
- **POSIX 清理**：`start_new_session=True` 建独立进程组，`os.killpg(pgid, SIGKILL)` 杀整组（[posix.py:18](src/codeagent/tools/execution/posix.py#L18)）。这能杀掉 `bash -c "cmd1 | cmd2 &"` 派生出的所有子进程。
- **Windows 清理**：`CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW` + `taskkill /F /T`，但**明确返回 `False`**——因为 MSYS/Git Bash 的子进程可能被重新挂到别的进程树，**无法证明全树已停**。所以 Windows 上 `cleanup_confirmed=False`，状态是 `uncertain`。
- **输出**：重定向到临时文件（`tempfile.mkstemp`），流式统计总字节/总行数，只物化有界预览到内存（`max_memory_bytes=1MB`）。这样 `yes | head -c 1G` 不会把内存打爆。
- **截断方向**：bash 保留**末尾**（`truncate_tail`，因为超时/报错信息通常在最后），read/grep/find/ls 保留**开头**（`truncate_head`）。

**追问：为什么要 temp file 而不是 PIPE？**
PIPE 有 64KB 缓冲，进程写满会阻塞；而且如果父进程不读，子进程会永久挂起。temp file 没有这个限制，还能事后计算精确总量。

---

### ★6.7 MCP 怎么接入的？

**答案骨架**：官方 `mcp` SDK，**stdio 传输 + 后台线程 + 独立事件循环**（因为 SDK 是同步的，而我们的运行时是 asyncio）。

- 启动时读 `~/.codeagent/mcp.json`，每个 server 起一个子进程，握手后 `tools/list` 拉工具清单。
- 工具名**命名空间化**：`mcp__<server>__<tool>`，避免和内置 8 个工具撞名。
- 每个工具包成一个 `AgentTool`，`execute` 时桥接到后台循环的 `tools/call`。
- 有**分组预算**（每个 server 的工具数有上限），防止某个 MCP server 塞 200 个工具把 system prompt 撑爆。
- 关闭时统一 `close_mcp_tools()`，否则子进程泄漏。

**追问：MCP 工具被投毒怎么办？（提示注入）**
这是真实风险。现状：MCP 工具的调用仍然过 `classify_tool`（`classify_mcp` 分支按 server/tool 名的权限规则判定），所以**配置层面能限权**。但**工具返回的内容里的注入指令没有任何检测**——模型读到 "ignore previous instructions" 会照做。诚实答案：这是所有 MCP 客户端的通病，缓解手段是"危险操作仍需确认"+ 输出边界，不是内容检测。

---

### 6.8 多工具并发写同一个文件会怎样？

**答案骨架**：[mutation_queue.py](src/codeagent/tools/shared/mutation_queue.py)——按**绝对路径**上 `threading.Lock`，只包写类工具（write/edit），读类不锁。

关键约束写在 docstring 里：**调用方必须先 `resolve_to_cwd()` 把路径解析成绝对路径再进队列**，因为锁是按字符串做 key 的，`./a.txt` 和 `a.txt` 会命中两把不同的锁。这是个很典型的"隐式契约"，面试官可能会问"怎么保证调用方遵守"——诚实说：靠代码审查 + 单元测试，没有类型级保证。

---

## 7. 上下文治理主线

### ★7.1 预算里最重要的三个数是什么？

**答案骨架**：

```
input_budget = context_window - output_reserve - reserve_tokens
headroom     = input_budget - input_tokens
```

- `context_window`：模型窗口（来自 `ModelSpec.context_window`，缺省 128k）。
- `output_reserve`：给输出留的（默认 4096）。
- `reserve_tokens`：安全余量（默认 16384）。

`input_tokens` 的组成是四块分开估的：`system_prompt` / `tool_definitions` / `conversation` / `tool_results`。分开估的目的是**诊断**——`--context` 能告诉你"是工具定义太多还是历史太长"。

---

### ★7.2 token 怎么估的？准吗？（软肋，见 §11.1）

**答案骨架（设计）**：`len(text) // 4` 字符数除以 4，工具定义按 `json.dumps(sort_keys=True, separators=(",",":"))` 序列化后同样除 4。中文/俄文等非 ASCII 按字符算，**这会低估**（一个中文字符通常 1–1.5 token，但按 1/4 算成了 0.25 token）。

为什么仍然用它：① 零依赖、零延迟、完全确定性（测试可写死期望值）；② 配了 `reserve_tokens=16384` 和 `trigger_headroom=2048` 做缓冲；③ preflight 是**阻断前最后一道**而不是唯一一道——真正的兜底是 provider 返回 400 和压缩。

**诚实答案**：我的估算公式对中文严重低估（实测 21 个中文字估出 5 tokens，实际约 15–20）。改进方向：按 Unicode 区块加权（CJK 记 1 token/字，ASCII 记 1/4），或者用 tiktoken 的可选依赖，或者**用真实 usage 反推校准系数**（`record_actual_usage` 已经存了真实 input_tokens，可以算估算/真实的比值做滑动平均）。

---

### ★7.3 四态 preflight 各自做什么？

**答案骨架**（[preflight.py](src/codeagent/core/context/preflight.py)）：

| 状态 | 条件 | 动作 |
|---|---|---|
| `uncertain` | `window_source` 不在 `{catalog, override, provider}` | 按 `uncertain_budget_policy` 决定 allow/fail |
| `over_limit` | `headroom < 0` | **`allowed=False`，抛 `ContextPreflightError` 阻断请求** |
| `near_limit` | `headroom <= warning_boundary`（默认 2048） | `allowed=True`，只发警告事件 |
| `safe` | 其余 | 正常放行 |

**关键点**：`near_limit` **不阻断**。这是有意的——否则 128k 窗口的模型在 126k 时就被拒绝，用户会觉得"明明还能用"。真正处理 near_limit 的是**压缩**（0.8 触发）。

**追问：`uncertain` 为什么默认 allow？**
因为老模型适配器描述不了自己的窗口，如果默认 fail 会直接不可用。但可以配成 `fail` 做硬边界（`uncertain_budget_policy="fail"`）。

---

### ★7.4 工具结果裁剪的算法是什么？可逆吗？

**答案骨架**（[budget.py:154](src/codeagent/core/context/budget.py#L154) 的 `govern_tool_messages`）：

1. 算出**非工具消息**占了多少 token。
2. `available = input_budget - non_tool_tokens`，这就是所有工具结果能分到的总额。
3. **按条均分**：每条先给 `remaining / remaining_count`，够就原样保留，不够就裁到配额。
4. 裁剪时**先保留元数据摘要**（`[工具结果元数据] 完整性=truncated, 路径=..., 总字节=..., 原因=request_budget`），再填内容前缀，最后加 `[工具结果已按请求预算裁剪]` 标记。
5. 返回的是**新列表**（`_clone_message` 深拷贝），**原历史一个字节不动**。

**可逆性**：**部分可逆**。原消息还在会话历史/JSONL 里，只是**这一请求的视图**被裁了。但模型看到的是裁过的内容，如果它需要后面被裁掉的部分，只能重新调工具（比如 read 带 offset）。

**追问：为什么不按"最近优先"分配？**
因为按条均分对模型更友好——它知道每条结果大概都还在，不会出现"第一条完整、后面全空"的极端。代价是"重要的长结果被平均削弱"。这是可配置的取舍点。

---

### 7.5 预算事件为什么"每请求恰好一次"？

**答案骨架**：这是 [CHANGELOG 未发布条目](CHANGELOG.md) 里的真实修复。之前 `prepare_context` 在"工具结果被裁剪"时会发两次 `CONTEXT_BUDGET`（一次裁剪前、一次裁剪后），payload 完全相同，导致订阅方把一次请求的预算变化计成两次（TUI `/context` 和 headless `--context` 都受影响）。

修复：裁剪后**重算**预算，但只在最后 `emit` 一次。并且补了"按事件计数"的回归测试（`tests/core/test_context_budget.py`）。

**这个故事为什么好**：它体现"可观测性本身也是契约"——同一份数据发两次不是"多此一举"，而是会让下游统计出错。

---

## 8. Subagent 主线

### ★8.1 `delegate` 是工具还是 Agent？

**答案骨架**：**模型侧是工具，运行时侧是独立 Agent**（[delegate_tool.py](src/codeagent/app/composition/subagent/delegate_tool.py)）。

- 模型看到的是普通 `AgentTool`：`name="delegate"`，参数 `task` / `profile` / `context` / `budget`。
- 实际执行时，它创建一个**独立的子 Session + 独立 Agent 实例**：自己的上下文、自己的事件总线、自己的 run_id、自己的资源关闭边界。
- 子 Agent **不继承父历史**，只拿到显式传的 `task` + `context`（`fact` / `constraint` / `output_requirement` 三类，有字符上限）。
- 子 Agent 的工具白名单固定为 `read/grep/find/ls/skill`，**不含 `delegate`**（所以深度天然受限），不含任何写工具。

**追问：为什么"工具接口"和"Agent 生命周期"要分层？**
因为如果直接把子任务文本追加到父上下文，会同时坏三件事：上下文膨胀（子任务的完整 transcript 进父级）、权限继承不透明（子 Agent 拿到父的全部工具）、失败不可归因（分不清是子任务失败还是父级编排失败）。

---

### ★8.2 预算和硬上限具体是多少？

**答案骨架**（[core/subagent/policy.py](src/codeagent/core/subagent/policy.py)，领域规则在 core，应用层不维护第二份）：

| 项 | 默认 | 硬上限 |
|---|---|---|
| `max_turns` | 8 | 16 |
| `max_tool_calls` | 32 | 64 |
| `timeout_seconds` | 120 | 300 |
| `max_output_chars` | 8000 | 16000 |
| 单次父运行子任务数 | 4 | — |
| 委派深度 | 1 | 1 |

**为什么放 core 而不是 app**：AGENTS.md 里明确写了"应用层不得自行维护第二份预算默认值或上限常量"。因为如果 app 和 core 各有一份，改一处忘一处就会出"UI 说 8 轮实际跑 16 轮"的问题。`app/composition/subagent/budget.py` 只做"把不可信的模型输入解析成 `SubagentBudget` 再调 core 的 `resolve_budget`"。

---

### ★8.3 准入顺序是什么？为什么顺序重要？

**答案骨架**（[admission.py](src/codeagent/core/subagent/admission.py) 的 `admit_request`）：**先校验、后占资源**。

顺序：① profile 合法 → ② context 字段合法（未知字段/空值/超限） → ③ budget 合法（未知字段/null/超硬上限） → ④ 深度是否允许 → ⑤ 配额是否还有 → ⑥ 槽位能否预留。

**为什么顺序重要**：所有拒绝都必须发生在"创建子 Session、占用配额、调用模型"**之前**。否则一次非法请求会留下一个幽灵子运行记录、消耗一个槽位、甚至已经发了一次模型请求（花钱）。这是"fail fast 且无副作用"的典型实现。

---

### ★8.4 槽位仲裁（slot registry）解决什么问题？

**答案骨架**（[slots.py](src/codeagent/core/subagent/slots.py)）：两个不变量。

1. **同一个 `delegation_id` 绝不能有两个活着的子运行**（重复预留直接返回 False）。
2. **容量上限**（`capacity`）——满了就拒绝，不是排队。

注意区分**并发配额**和**累计配额**：`SubagentSlotRegistry` 管的是**并发**（正在跑的），而"单次父运行最多 4 个子任务"是**累计**，所以在 `delegate` 工具边界上计数（docstring 明确写了这个分工原因）。

---

### ★8.5 终态归因怎么做的？

**答案骨架**：区分三种"没成功"，因为它们的处理完全不同：

- `parent_cancelled`：父被取消 → 子也要取消，清理不确定时保留 `cleanup_uncertain`。
- `timeout`：墙钟超时（覆盖排队 + 启动 + 模型/工具执行 + 确认等待，不只是模型时间）。
- `budget_exceeded`：轮数/工具数/输出字符数超了。

**终态只发布一次**（`subagent_finished` 唯一），迟到事件、重复终态按 `delegation_id` 折叠。为什么强调"一次"：父子事件是两套序列（`child_sequence` / `parent_sequence`），如果终态发两次，父级的运行记录会重复计数、TUI 状态栏会显示"失败 2 个"但实际只有 1 个。

---

### ★8.6 父级收回什么？为什么要"有界"？

**答案骨架**：**有界摘要 + 结构化证据，不要完整 transcript**。

- `SubagentResult` 里有：`summary`（截断到 8000 字符）、`findings`（最多 32 条）、`evidence`（每条带来源/位置/短摘录）、`usage`、至多一个 `artifact` 引用。
- **拒绝猜测**：如果子 Agent 只给了自然语言摘要，不会自动把它解析成 finding。悬空 evidence 引用、重复 evidence id、超限都判 `invalid_result`。
- 父会话还落一条**有界 `subagent` 记录**（状态/阶段/终态摘要/reason code/清理事实），进程重启时非终态记录折叠成 `abandoned/process_restarted`，**不创建子 Session、不产生幽灵运行、不回写原 JSONL**。

**追问：为什么不允许父级拿完整 transcript？**
两个原因：① 父上下文会膨胀（子 Agent 可能跑了 8 轮、32 次工具）；② 完整 transcript 里混着子 Agent 的试错过程，对父级是噪声。设计取向是"子 Agent 负责收敛，父 Agent 负责综合"。

---

## 9. 质量工程主线

### ★9.1 1711 个测试是怎么组织的？会不会有大量重复？

**答案骨架**：按被测边界分目录（`tests/core` / `tests/session` / `tests/ai` / `tests/tools` / `tests/app` / `tests/tui` / `tests/contracts`），**marker 按"跨了几个边界"分类**，不是按目录。

- `unit`（1041）：单模块、无外部进程。
- `contract`（521）：跨实现一致性、架构边界（分层解耦、规模门禁、双 Store 行为一致）。
- `integration`（114）：起真实子进程（MCP mock server）或多模块组合。
- `e2e`（15）：从 CLI 入口跑完整流程。
- `platform`（6）/ `security`（39）/ `performance`（20）/ `compatibility`（26）。

**防"测试注水"的三个机制**：
1. `test_scan_has_content` 这类**防空转断言**（"至少扫了 60 个文件""每层都有"）。
2. 架构测试本身是**参数化的**：`test_layer_import_rules` 对 337 个文件各一个用例——345 个用例但只有一个断言逻辑。
3. `conftest.py` 的 autouse fixture 检查**异步任务泄漏**：任何测试结束后如果还有 pending task，直接 `pytest.fail`。这条能抓住"测试自己写得不干净"。

**诚实补充**：345 个解耦用例确实拉高了"用例数"这个指标。所以我在简历里应该写"1711 个测试"时补一句"其中含 345 个按文件参数化的架构契约用例"，别让人以为都是独立业务场景。

---

### ★9.2 "全离线"怎么保证？

**答案骨架**：三重。

1. **`FakeClient`**：脚本化假模型（[fake.py](src/codeagent/ai/providers/fake.py)）。支持 `responses`（按序返回文本）、`steps`（按序返回带 tool_calls 的步骤，用于测 ReAct 多轮）、`usage`（注入 token 数）、`thinking`。并且记录 `call_history` 供断言"模型收到了什么"。
2. **`LLM_PROVIDER=fake`**：CLI/CI 全链路走假模型，`release_check.py` 装完 wheel 后也是用 fake provider 冒烟。
3. **HTTP 层用 `httpx.MockTransport`**：测传输/重试/错误分类时替换底层 transport，不发真实请求。

另外 `conftest.py` 有 autouse fixture 把 `config_mod.CONFIG_DIR` 重定向到 `tmp_path`，防止启动路径在真实的 `~/.codeagent` 里生成模板文件。

**但这个隔离有个洞（主动说）**：它只 patch 了模块变量 `CONFIG_DIR`，而 `Settings.model_config["env_file"]` 在**类定义时**就绑定了 `~/.codeagent/.env`，patch 之后不生效。缓解是：所有测试构造 `Settings` 时都显式传 `_env_file=None`；另外用 `HOME=/tmp/emptyhome` 跑全量仍然是 1711 passed，说明没有隐性依赖真实 HOME。

**追问：那真实 provider 的行为怎么验证？**
**没有在线测试**，这是明确的取舍（CI 不能有密钥）。缓解手段是：① `ProviderErrorKind` 分类有错误响应样例的单测；② SSE 解析有 7 个边界帧单测；③ `OpenAICompatClient` 的核心逻辑（SSE/重试/错误分类）用 `httpx.MockTransport` 覆盖了 5 个测试文件；④ 六家的差异被压缩到"base_url + model + reasoning 透传"。

**必须承认的空白**：真实 API 契约（字段名差异）、429 + `Retry-After` 的实际行为、流边界的真实分包方式。**换新 provider 时第一次真实调用仍可能踩坑。** 还有一个加固项：测试里**没有任何 socket 熔断机制**（搜不到 `respx` 或 socket patch），"离线"是**约定**而不是**强制**——某天有人写了个真发请求的测试，CI 不会拦住。

---

### ★9.3 覆盖率 86% 说明什么？不说明什么？

**答案骨架**：

- **说明**：绝大多数生产代码路径至少被执行过一次，且是**快速集（24–32 秒）**就跑出来的，不是靠慢测试堆的。
- **不说明**：断言强度。行覆盖不区分 `assert x` 和 `assert x is not None`，也不管 mock 是否让断言变成自证。
- **CI 硬下限是 80%**，不是 86%。定 80 是为了"新增模块即使覆盖低一点也不会立刻挂"，同时 86 这个实际值留了 6 个点的缓冲。

**加分回答**：如果要提升"有效覆盖率"，我会加两条：① 对安全分类器做**变异测试**（把 `deny` 改成 `allow`，看有没有测试挂）；② 对事务语义做**故障注入**（在 fsync 前后 kill 进程，验证恢复）。这两类比再多写 100 个 happy path 有用。

---

### ★9.4 mypy 分层棘轮是怎么工作的？

**答案骨架**（[type_scan.py](scripts/type_scan.py)）：

1. 对 5 个层各跑一次 `mypy src/codeagent/<layer>`，用正则从输出里抽 `Found N errors`。
2. 和 [docs/type-baseline.json](docs/type-baseline.json) 比较：**任何一层比基线高就 fail**。
3. 比基线低时**不 fail，只提示**"可以用 `--update` 固化"。

**为什么分层而不是一刀切**：一次性让全仓 strict 通过会混进几千条历史债务，任何一个功能 PR 都会被淹没。分层 + 只降不升，让债务可以"按层、按 PR"逐步还。

**追问：这不会变成数字游戏吗？（诚实回答，见 §11.7）**
会，如果只盯着数字。所以配了三道防线：① 禁止为了过门禁放宽 `pyproject.toml` 的 mypy 配置（写在 AGENTS.md 里）；② `--update` 只在债务下降时用；③ 基线文件本身是 10 行的 JSON，**任何下降都会在 diff 里显式出现**，reviewer 能看到。

---

### ★9.5 1060 → 22 是怎么做到的？（这是最容易被追问的一条）

**答案骨架**：**不是逐条修 1000 个，而是一次结构性收敛。** 必须这么讲，否则被问"你怎么改的 1000 个错误"就答不上来。

诊断结果：1060 条里 **`app` 的 609 条 + `session` 的 270 条都是同一个 `attr-defined`**——mixin 里访问宿主类（`AgentSession` / `Agent` / `TaskSupervisor` …）的属性，mypy 看不到。

解法：为每个 mixin 组合建一个**纯类型声明的宿主基类**（`AgentSessionHost` / `AgentHost` / `TaskSupervisorHost` …，共 11 个 `host.py`），里面只有类级类型注解，**零赋值、零方法体**。mixin 继承它，mypy 就能解析属性；运行时行为完全不变（宿主的 `__init__` 真实赋值会覆盖声明）。

效果：`app` 696 → 17，`session` 311 → 5。**一次提交解决 879 条**，剩下的 22 条是真正的类型问题，保留了基线。

**追问：为什么不干脆加 `# type: ignore`？**
因为 ignore 会掩盖**将来的**同类错误。宿主基类的声明是"一次声明，永久生效"，而且新增 mixin 属性时忘记在宿主声明会**立即可见**。全仓现在只有 4 处 `type: ignore`（session 3、app 1）。

**追问：这算不算降低标准？**
不算降低、也不算提高——它是**把"结构不可见"和"类型错误"区分开**。但**必须承认**：`--strict` 下仍有 100 个错误（`no-untyped-def` 31、`attr-defined` 20、`no-any-return` 16…），说明类型质量还不到"严格通过"的水平。

---

### 9.6 规模门禁（300/80）解决什么问题？

**答案骨架**：它不是风格规定，是**可测试性的代理指标**。一个 800 行的文件通常意味着"多个职责耦合在一起，没法单独测"。设成可执行门禁后，触发拆分是**强制的**，不是靠自觉。

现状：全层 337 个文件、1824 个函数，**最长文件 300 行、最长函数 80 行**（`create_agent_session`）。`COMPATIBILITY_EXCEPTIONS` 是空的——意味着**没有任何豁免**。

**追问：拆分是不是把复杂度藏起来了？**
有风险。拆成 10 个 100 行的 mixin，总复杂度没降。所以真正的约束是**拆的方向**：按"职责"拆（compaction / persistence / lifecycle），不是按"行号"拆。而且拆完要有测试证明行为没变——v0.5 那次拆分（`classifier.py` → `ask_rules.py` 等 6 处）明确写了"外部行为与公共接口未变"。

---

### 9.7 CI 的四个 job 分别干什么？

**答案骨架**（[ci.yml](.github/workflows/ci.yml)）：

| job | 内容 | 阻塞? |
|---|---|---|
| `quality-fast` | ruff check（E9/F821/F841）→ ruff format --check → **type_scan** → 快速集测试 + 覆盖率 ≥80% → 版本一致性 → `git diff --check` → **openspec validate --specs** | 是 |
| `test-matrix` | ubuntu/windows/macos 三平台跑 `integration or e2e or platform or compatibility` | 是 |
| `package-smoke` | 构建 wheel/sdist → 检查内容与敏感文件 → 干净环境安装 → fake provider CLI 冒烟 | 是 |
| `performance` | TUI 基准四场景，和基线比较，产出 artifact | **否**（`continue-on-error: true`） |

**追问：性能为什么不阻塞？**
因为 GitHub runner 的抖动会让相对回归线（20%）经常误报。所以策略是"硬上限（p95 ≤ 33ms、dropped_frames = 0）仍然比较，但只告警；发布候选必须用 `--fail-on-regression`"。**诚实说：这是折中，不是理想状态。**

---

### 9.8 OpenSpec 是干什么的？24 份规格怎么用？

**答案骨架**：规格驱动开发（spec-driven）。每份 `openspec/specs/<name>/spec.md` 用固定格式写 `Requirement` + `Scenario`（WHEN/THEN），然后：

- 新功能先写 change（`openspec/changes/`），实现完归档进 `specs/`；
- `openspec validate --specs` 校验格式和场景完整性，**在 CI 里阻塞**。

**价值**：给了"需求 → 测试"的映射锚点。比如 `task-mode-verification` 里写了"规划模式拒绝写入 → 文件不发生变化，工具返回拒绝原因和切换提示"，对应的测试就能直接按 scenario 命名。

**追问：24 份是不是过度文档化？**
对一个个人项目，是偏重的。但它带来一个实际好处：**改行为时能查到"当初为什么这么定"**。比如 `context-budget-preflight` 的 spec 明确写了 preflight "no compaction, no truncation, no provider calls"，这就是我 §7.3 那张表的设计依据。

---

## 10. 现场演示脚本（10 分钟）

面试官说"给我看看"时，按这个顺序走，**每步都有输出，不空转**：

```bash
# 0) 环境（10 秒）
.venv/bin/python -V && git log --oneline -1

# 1) 离线跑通完整闭环（20 秒）——这是"零配置可验证"的证明
LLM_PROVIDER=fake .venv/bin/python -m codeagent --prompt "你好"
# 输出：你: 你好 / 测试回复

# 2) 全量测试（36 秒）——边跑边讲分层
.venv/bin/python -m pytest -q --strict-markers
# 输出：1711 passed in 36.06s

# 3) 快速集 + 覆盖率（32 秒）——证明"日常反馈 30 秒"
.venv/bin/python -m pytest -m "unit or contract" -q \
  --cov=codeagent --cov-report=term | tail -3
# 输出：TOTAL 18451 2519 86% / 1562 passed

# 4) 三道门禁（各 1 秒）
.venv/bin/python scripts/type_scan.py        # 类型棘轮检查通过
.venv/bin/python scripts/scale_scan.py       # 生产代码规模检查通过（300/80）
.venv/bin/python -m pytest tests/test_decoupling.py -q | tail -2   # 345 passed

# 5) 现场演示一个安全判定（30 秒）——最有说服力的一段
.venv/bin/python - <<'PY'
from codeagent.tools.security import classify_tool
import tempfile
ws = tempfile.mkdtemp()
for cmd in ["rm -rf /", "git push origin main", "ls -la", "cat /etc/passwd"]:
    d = classify_tool("bash", {"command": cmd}, workspace=ws, cwd=ws,
                      exists=lambda t: False)
    print(f"{d.action:6} | {cmd:22} | {d.reason[:40]}")
PY
# deny   | rm -rf /             | 命令命中危险模式
# ask    | git push origin main| 推送远程分支
# allow  | ls -la              |
# allow  | cat /etc/passwd     |
```

**演示时不要做的事**：不要现场跑 TUI（终端状态不可控）、不要连真实 provider（网络不可控）、不要说"这个功能还没做完"超过一次。

---

## 11. 已知软肋：12 个会被问倒的点

> 原则：**主动说 > 被问出来**。每个都准备"一句承认 + 一句根因 + 一句改法"。

### 11.1 token 估算对中文严重低估

**实测**：21 个中文字符估出 5 tokens（`len//4`），真实约 15–20。
**根因**：按字符数除 4，隐含"平均 4 字符 = 1 token"的英文假设。
**改法**：CJK 按 1 token/字加权；或用真实 usage 反推校准系数；工具定义部分保留当前估算（JSON 以 ASCII 为主）。
**一句话**："估算器是保守的英文模型，中文会低估，所以靠 16k 预留和 preflight 双重兜底——但这是我明确知道的精度缺口。"

### 11.2 索引每次 append 都全量重建（O(n²)）

**实测**：1500 次 append 触发 1500 次全量重建，耗时 6.06 秒；`apply_record` 增量分支**实际走不到**。
**根因**：`_append()` 的顺序是"先写 JSONL → 再 `_read_valid_index()`"，而索引的指纹是上一次写完之后取的，所以每次都必然不匹配。
**改法**：调整顺序为"读索引（此时文件还是索引记录的版本）→ `apply_record` 追加 → 写 JSONL → 用新指纹写索引"。
**一句话**："设计上是增量索引，实现上顺序反了，导致退化成 O(n²)；现有测试只覆盖了'列表/查询命中索引'，没覆盖'追加后索引仍有效'。"

### 11.3 取消发生在提交窗口时，内存与磁盘分叉

**实测**：在 `commit_turn_async` 完成后、`_history = kept_history` 之前取消 → 内存 `history=[]`，磁盘已有 user+assistant 两条消息，`last_outcome` 却是 `cancelled / rolled_back`。
**根因**：`AsyncPersistenceBoundary` 用 `shield` 保证"写不半途抛弃"，但写完之后到内存赋值之间没有原子性。
**改法**：把"提交已开始"作为状态写入 `RunOutcome`（`commit_status=COMMITTED` + `post_commit_status=cancelled`），或者恢复时以磁盘为准。
**一句话**："'成功才落盘'在正常失败路径成立，但在'提交已经开始'这个窗口里，磁盘已经是真相，内存回滚会让两者不一致。"

### 11.4 `create()` / `append_message()` 缺少 session_id 路径校验

**实测**：`store.create("../escaped")` 成功在 sessions 目录**之外**创建文件；`delete()` 有 `_validated_session_path` 校验，`recovery_report` 也返回 `invalid_session_id`，但 create/append/fork 没有。
**现网可达性**：`SessionManager` 只传 uuid4，**UI 不可达**；但 `SessionStore` 是公开端口。
**改法**：把 `_validated_session_path` 收敛到 `_path()` 里（所有入口统一），或加一个 `_safe_path()` 装饰器。
**一句话**："写路径只有 delete 做了 id 校验，create/append 没做；当前调用方是安全的，但端口边界不闭合。"

### ★11.5 命令包装器可以完全绕过安全判定（最严重的一条）

**实测（全部返回 `allow`，不是 `ask`）**：

```
allow  | timeout 5 rm -rf ~          ← 只差一个 timeout 前缀
allow  | nice -n 5 rm -rf ~/d
allow  | env -i rm -rf /tmp/x
allow  | command rm -rf /tmp/x
allow  | bash -lc 'rm -rf ~'         ← -lc 不是 -c
allow  | python3.12 -c "import os"   ← 带版本的解释器名
allow  | foo=$(rm -rf ~)             ← 变量赋值内的命令替换
```

而裸 `rm -rf ~` 是 `deny`（命中 `_dangerous_intent` 的"删除目标为用户主目录"）。

**根因**（三处叠加）：
1. `_dangerous_intent` 用 `_effective_command_index()` 定位"真正的命令"，但它的跳过表只有 `("sudo","env","time","nohup","command")`——**没有 `timeout`、`nice`、`xargs`**，而且跳过 `env` 后没有跳过 `env` 的参数（`-i`），所以 `env -i rm` 的"真正命令"被算成了 `-i`。
2. `ask_rules` 的匹配只看 `segment[0]`，所以 `timeout 5 rm -r` 的首 token 是 `timeout`，`rm -r` 规则不命中。
3. `_strip_substitution` 只认 `$(...)` 开头的 token，不认 `foo=$(...)`；`_INTERPRETER_WRAPPERS` 是精确集合，`python3.12` / `bash -lc` 都不在。

**这意味着什么**：**安全判定是"字面量模式匹配"，一个前缀就能绕过。** 危险命令黑名单的价值只在"模型直接说要删库"时生效，挡不住"模型从网上抄来的命令"。

**改法（按性价比排序）**：
1. 把"定位真实命令"从白名单跳过表改成**语义解析**：识别所有 POSIX 包装器（`timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec`）并跳过其参数，直到第一个"非选项、非赋值"的 token。
2. 危险判定对**所有段的所有 token** 做子串扫描（而不只是 `segment[0]`），宁可误报。
3. `$(...)` / 反引号 / `${...}` 一律先递归展开再判定；无法展开时**默认 DENY**。

**一句话**："我的安全判定是字面量级的——`timeout 5 rm -rf ~` 能过，因为定位真实命令的跳过表漏了 `timeout`。这是我最想重做的一块，正确做法是语义解析 + 无法确定就拒绝。"

### ★11.6 敏感路径正则对**普通单词**误杀

**实测**：

```
deny | echo secret            ← token 是 "secret"
deny | grep -r SECRET src     ← token 是 "SECRET"
deny | cat .env.example
```

**根因**：`_SECRET_PATH_RE` 里有一条 `(?:credentials|secrets?|tokens?)(?:$|\.(?:json|ya?ml|toml|ini|cfg|conf))`，`_secret_path_hit` 对**每个 token** 做 `search`，所以任何以 `secret`/`token` 结尾的**单词**（`$` 锚点匹配字符串末尾）都命中。`echo secret` 里 `secret` 是完整 token → 直接 deny。

**影响**：这是个**功能性阻塞**——模型说 `grep -r SECRET src` 查硬编码密钥（这恰恰是安全审查的正常动作）会被拒。而且 `.env.example` 被 deny，模型读不到项目最常见的配置模板。

**改法**：这条规则只应该匹配**路径形态**的 token（包含 `/` 或 `\`，或以 `.` 开头的文件名），不应该匹配裸单词；`.env.example`/`.env.sample`/`.env.template` 加白名单。

**一句话**："威胁模型是'文件名'，但实现成了'任意 token 的正则搜索'，结果 `echo secret` 这种命令直接被拒——误报率比漏报更伤害可用性。"

### 11.7 grep / find / ls 完全没有工作区边界

**实测**：`grep {"path": "~/.ssh"}`、`find {"path": "/"}`、`ls {"path": "~"}` 全部 `allow`。

**根因**：`_BOUNDED_TOOLS = ("read", "write", "edit")`——只有这三个工具走 `classify_file`。而 `grep`/`find`/`ls` 能读取任意路径，且 `grep` 还能把匹配内容原样返回。

**这比 bash 更值得修**：因为 `grep ~/.ssh/id_rsa` 不需要 bash 权限就能把私钥内容读进上下文。虽然 `read` 对 `.ssh` 是 deny，但 `grep` 绕过了。

**一句话**："文件边界只覆盖了 read/write/edit，grep/find/ls 是裸的——这是个明确的漏洞，`grep ~/.ssh` 就能读到私钥。修法是把边界检查下移到 `resolve_to_cwd`/`FsOps` 层，而不是每个工具自己调。"

### 11.8 越界读取的"警告"模型看不到

**实测/代码确认**：`classify_file` 对越界读返回 `SecurityDecision(ALLOW, "越界读取: ...", warning=True)`，但 `session/runtime/execution.py` 的 `before_tool_call` **只读 `decision.action`**，`warning` 字段被丢弃，不进模型可见文本。

**影响**：设计意图是"放行但让模型知道越界了"，实际是"静默放行"。这是"意图与实现脱节"的典型。

**一句话**："我设计了 warning 通道，但适配层只读了 action，所以越界读取对模型完全透明——这是我在写这份材料时才发现的。"

### 11.9 bash 双流各 30k，合并后模型可见约 60k

**实测**：`stdout` 40000 字节 + `stderr` 40000 字节 → 工具返回 **60073 字符**。

**根因**：`MAX_OUTPUT_CHARS = 30_000` 是常量但**没被使用**（死常量），实际生效的是 `ToolResourceLimits.max_output_bytes`，而 stdout/stderr 各自独立截断到 30k。

**影响**：单次工具结果能到 60k 字符 ≈ 15k token（按 `len//4`）或更多（含 CJK），一次就能吃掉大半预算。

**一句话**："输出上限是 per-stream 的，合并后能翻倍；`MAX_OUTPUT_CHARS` 这个常量是死的。应该在合并后统一再截一次。"

### 11.7 mypy 配置宽松，`--strict` 下仍有 100 个错误

**实测**：`[tool.mypy]` 只有 `python_version` / `ignore_missing_imports` / `follow_imports`，**没有 `strict`、没有 `check_untyped_defs`、没有 `disallow_untyped_defs`**；`mypy src/codeagent --strict` = 100 errors（`no-untyped-def` 31、`attr-defined` 20、`no-any-return` 16）。
**注解覆盖率**：1794/1824 函数有完整注解（98.4%）。
**一句话**："棘轮保证的是'不倒退'，不是'严格通过'。剩下的 22 条是真实类型问题；`--strict` 的 100 条里大部分是 `Any` 返回和少量未注解函数，属于可以排期的债务。"

### 11.8 覆盖率是行覆盖，不衡量断言强度

见 §9.3。补一句："我会用变异测试对安全分类器做补强——把 `DENY` 改成 `ALLOW`，看有几条测试会挂。"

### 11.9 没有真实 provider 的在线测试

见 §9.2。补一句："换 provider 的第一次真实调用仍可能踩坑，所以 `ProviderErrorKind` 分类和 SSE 边界帧是重点测的。"

### 11.10 性能基准非阻塞 + 只在 Linux runner 上有意义

见 §9.7。补一句："硬上限（p95 ≤ 33ms、dropped_frames = 0）仍在比较，只是不 fail；发布候选才强制。"

### 11.11 Subagent 只有串行 + 只读 + 深度 1

**现实**：没有并行委派、没有子 Agent 写权限、没有工作区合并、没有跨进程恢复。
**为什么这么定**：并行委派会引入"多个子 Agent 同时改同一个文件"的冲突，需要工作区隔离或合并策略——这是个独立的大问题，MVP 故意不做。
**一句话**："v0.5 的边界是'只读、串行、深度 1'，因为写权限和并发合并是另一个量级的问题；现在的价值是证明'委派契约 + 预算治理 + 有界结果回传'这套骨架成立。"

### 11.12 没有沙箱：bash 就是全权限

**现实**：`bash` 工具能执行任意命令，安全判定是"事先分类"而不是"执行时隔离"。没有容器、没有 seccomp、没有 chroot。
**一句话**："这是本地单用户工具的定位——用户在自己机器上跑，威胁模型是'模型误操作'而不是'恶意租户'。真要隔离得上容器或 OS 级沙箱，那是另一套架构。"

---

## 12. 简历口径校正

| 简历原文 | 建议改法 | 原因 |
|---|---|---|
| "约 1.8 万行 Python" | **"约 3 万行 Python（含 1700 测试 / 2.8 万行测试代码）"** | 实测 src 纯代码 28887 行 |
| "1700+ 离线自动化测试（覆盖率 84%）" | **"1711 个离线测试，快速集 1562 个 / 覆盖率 86.35%"** | README 已更新；且"快速集 30 秒"比总数更有说服力 |
| "mypy 分层棘轮门禁，主导类型债务从 1060 项降至 22 项（削 97.9%）" | **保留数字，但补一句方法："其中 879 条是 mixin 宿主属性不可见（attr-defined），通过 11 个纯类型声明 Host 基类一次性收敛"** | 否则被问"怎么改 1000 个错误"答不上来 |
| "四层 CI 流水线" | **保留**（quality-fast / test-matrix / package-smoke / performance） | 准确 |
| "契约测试强制分层依赖边界" | **可加"337 个文件的 AST 扫描，345 个参数化用例"** | 具体数字更有力 |
| "会话持久化…查询索引" | **建议改成"追加式 JSONL + 文件锁 + 可重建索引"**，别说"高性能索引" | 索引有 O(n²) 重建问题（§11.2） |
| "长会话 10000 blocks 基准验证性能不随历史线性衰减" | **补"渲染时间不随历史增长（1.4/3.9/7.1ms），但峰值内存仍随 transcript 线性增长（2→9.7→19.3MB）"** | 主动说内存，避免被追问时被动 |
| "危险命令三级安全判定" | **保留，但准备一句"bash 重定向不做路径边界，见 §11.5"** | 主动交底 |

**最需要改的一条**：§11.2 的索引问题。如果面试官真的去跑 benchmark 或读 `_append`，这是唯一一个"宣称和实现有明确差距"的地方。**建议投递前花 30 分钟把它修掉**（调整三行顺序 + 补一个"追加后索引仍有效"的测试），然后把 §11.2 从软肋列表删掉。

---

## 13. 反问环节（问什么显得你真做过）

1. "团队现在是怎么评估 Agent 改动的？有没有类似'固定任务集 + 通过率'的回归集，还是主要靠人肉试用？"——展示你知道 Agent 的评测是真问题。
2. "线上如果模型返回了非法工具参数，你们是在协议层重试还是把错误回填给模型？"——对应 §4.4。
3. "上下文压缩这块，你们会做保真度评估吗？还是只保证不超限？"——对应 §5.9。
4. "安全这块，是走'事先分类 + 用户确认'，还是有执行时隔离（容器/沙箱）？"——对应 §11.12。
5. "这个岗位更看重 Agent 能力的广度（多模态/多 Agent/工具生态），还是工程可靠性（可观测/评测/治理）？"——把自己定位到后者。

---

## 附录 A：必背代码位置速查

| 主题 | 位置 |
|---|---|
| ReAct 主循环 | [loop.py](src/codeagent/core/orchestration/loop.py) `_run_agent_loop` |
| 单轮编排 | [turn.py](src/codeagent/core/orchestration/turn.py) `run_turn` |
| 工具批并发/保序/取消 | [batch.py](src/codeagent/core/orchestration/batch.py) `execute_tool_batch` |
| 工具执行运行时 | [runtime.py](src/codeagent/core/execution/runtime.py) `ToolExecutionRuntime` |
| 端口定义 | [ports.py](src/codeagent/core/contracts/ports.py) |
| 事件类型（40） | [events.py](src/codeagent/core/contracts/events.py) `EventType` |
| 预算估算 | [budget.py](src/codeagent/core/context/budget.py) `estimate_context_budget` |
| 工具结果裁剪 | [budget.py](src/codeagent/core/context/budget.py) `govern_tool_messages` |
| preflight 四态 | [preflight.py](src/codeagent/core/context/preflight.py) `evaluate_context_preflight` |
| 模型请求（预算+流式装配） | [request.py](src/codeagent/core/model/request.py) `new_model_message` |
| SSE 帧边界 | [streaming.py](src/codeagent/ai/transport/streaming.py) `stream` |
| SSE 单帧解析 | [sse.py](src/codeagent/ai/transport/sse.py) `SSEParser.feed` |
| 错误分类 | [errors.py](src/codeagent/ai/errors.py) `classify_provider_error` |
| 重试退避 | [retry.py](src/codeagent/ai/transport/retry.py) `retry_delay` |
| 安全三档 | [classifier.py](src/codeagent/tools/security/classifier.py) `classify_bash` |
| 危险模式 | [bash_rules.py](src/codeagent/tools/security/bash_rules.py) `DANGEROUS_PATTERNS` |
| ASK 规则表（约 20 条） | [ask_rules.py](src/codeagent/tools/security/ask_rules.py) `default_ask_rules` |
| 文件边界 | [filesystem.py](src/codeagent/tools/security/filesystem.py) `within_workspace` |
| 并发写串行化 | [mutation_queue.py](src/codeagent/tools/shared/mutation_queue.py) |
| 输出截断 | [truncate.py](src/codeagent/tools/shared/truncate.py) |
| 进程组击杀 | [posix.py](src/codeagent/tools/execution/posix.py) / [windows.py](src/codeagent/tools/execution/windows.py) |
| JSONL 写入 + fsync | [writing.py](src/codeagent/session/persistence/jsonl/writing.py) `_append` |
| 回滚（truncate 到原始 size） | [writing.py:112](src/codeagent/session/persistence/jsonl/writing.py#L112) `_restore_append` |
| 提交/失败/取消编排 | [run_coordinator.py](src/codeagent/session/run_coordinator.py) |
| 恢复三态 | [recovery.py](src/codeagent/session/persistence/jsonl/recovery.py) `recovery_report` |
| 文件锁 | [locking.py](src/codeagent/session/persistence/locking.py) `PathLock` |
| 压缩策略（0.8/0.65） | [policy.py](src/codeagent/session/compaction/policy.py) |
| 压缩执行 | [compaction_runtime.py](src/codeagent/session/compaction_runtime.py) |
| Subagent 领域规则 | [policy.py](src/codeagent/core/subagent/policy.py) / [admission.py](src/codeagent/core/subagent/admission.py) / [slots.py](src/codeagent/core/subagent/slots.py) |
| 分层解耦测试 | [test_decoupling.py](tests/test_decoupling.py) |
| 规模门禁 | [scale_scan.py](scripts/scale_scan.py) |
| 类型棘轮 | [type_scan.py](scripts/type_scan.py) / [type-baseline.json](docs/type-baseline.json) |
| CI | [.github/workflows/ci.yml](.github/workflows/ci.yml) |

## 附录 B：三个可以现场敲的"证明脚本"

```bash
# 1) 证明"成功才落盘"（正常失败路径）
.venv/bin/python -m pytest tests/session/behavior/test_finalization_contract.py -q

# 2) 证明安全三档（见 §10 第 5 步）

# 3) 证明类型棘轮只降不升
.venv/bin/python scripts/type_scan.py --update && git diff docs/type-baseline.json
```
