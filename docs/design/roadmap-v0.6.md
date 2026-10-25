# tenon v0.6 路线图:从"可验证底座"到"可托付运行时"

> 状态: 提案(2026-10-22)
> 事实来源: `src/` 约 3.6 万行、`tests/` 约 2.8 万行、24 份 OpenSpec 主规格;快速质量集 1562 passed / 24.77s;规模门禁与类型棘轮当日通过。
> 本文把一次横向评审(与 Pi Agent SDK、the coding assistant 对比 + 四项实测)收敛为可验收的路线,近期三项拆成 OpenSpec change 并进入实现。

## 1. 结论

tenon 的稀缺资产不是功能数量,而是**可验证性**:分层契约由 AST 扫描强制、单文件 ≤300 行/单函数 ≤80 行的规模门禁覆盖全部生产层、类型债务棘轮只降不升、fake provider 让 1562 个测试在 25 秒内离线跑完。Pi 与 the coding assistant 均未对外承诺这一层。

同时存在两类问题,优先级不同:

1. **正确性缺陷**(可实测,已证伪当前实现的部分承诺):安全分类可被前缀绕过、bash 合并输出无上限、中文 token 四倍低估、会话索引追加退化为 O(n²)。→ 必须先修,否则"安全""预算""性能"三个卖点都站不住。
2. **结构性代差**(不是缺功能,是执行模型不同):工具调用仍是"一次函数调用 = 一次模型往返"、`steer`/`followup` 未接通 UI、无后台作业、安全只有执行前分类而无隔离、子会话不可续跑。→ 需要独立版本,不在 v0.6 硬做。

## 2. 实测证据

| # | 现象 | 证据 | 影响 |
|---|---|---|---|
| E1 | `timeout 5 rm -rf ~`、`nice -n 5 rm -rf ~/d`、`env -i rm -rf /tmp/x`、`bash -lc 'rm -rf ~'`、`foo=$(rm -rf ~)` 全部 `allow` | `classify_tool` 实测 | 危险命令黑名单可被一个前缀绕过 |
| E2 | `echo secret`、`grep -r SECRET src`、`read .env.example` 全部 `deny` | `classify_tool` 实测 | 正常安全审查动作被误杀,可用性受损 |
| E3 | `grep {"path":"~/.ssh"}`、`find "/"`、`ls "~"` 全部 `allow` | `classify_tool` 实测 | 文件边界只覆盖 read/write/edit |
| E4 | 越界读的 `warning` 在 `session/runtime/execution.py` 被丢弃 | 代码确认 | "放行但提示模型"的设计意图未生效 |
| E5 | 40KB stdout + 40KB stderr → 返回 60073 字符,`truncated_by=None`;`MAX_OUTPUT_CHARS` 定义后无人使用 | `BashTool._invoke` 实测 | 单次工具结果可吃掉大半预算 |
| E6 | 50 个中文字符估为 12 tokens(实际约 50) | `estimate_tokens` 实测 | 预算 preflight 与压缩目标对小窗口中文会话失效 |
| E7 | append 100/200/400/800 次耗时 0.075s / 0.308s / 1.195s / 4.742s | `JsonFileStore` 实测 | 索引"增量"分支永远走不到,追加退化为 O(n²) |

## 3. 分层结论

| 层 | 结论 | 依据 |
|---|---|---|
| 编排内核 | 与 Pi 无代差(同为 ReAct + 事件流 + 双层 loop) | 架构文档与代码实读 |
| 工具范式 | 落后 the coding assistant 一代(程序化工具编排 vs 函数调用) | 对端 `run_code` 工具面 |
| 执行控制 | `steer`/`followup` 已实现但未接通 UI;无后台作业 | `interaction.py` 运行中拒绝输入;`followup` 全仓无调用方 |
| 安全 | 执行前分类(且可绕过),无执行时隔离 | E1~E4 |
| 上下文 | 结构完整(预算/压缩/裁剪),但估算与结果上限有精度缺陷 | E5、E6 |
| 持久化 | 结构最完整(JSONL 树 + fsync + 跨进程锁 + 恢复三态),但追加路径退化 | E7 |
| 多 Agent | 串行只读深度 1;子会话不可续跑 | `core/subagent/policy.py` |
| 可观测 | 约 40 类事件仅内部消费,无对外导出 | `headless` 仅文本输出 |
| 工程门禁 | 领先:规模/类型/格式/契约/离线全链路 | CI 与门禁实跑 |

## 4. v0.6 范围:三项正确性硬化

v0.6 只做"让已有承诺成立",不引入新执行范式。三项各自独立可发布、可回滚。

### 4.1 security-classification-hardening

- 包装器语义解析:识别 `timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec` 及其参数,定位真正被执行的命令。
- 命令替换递归展开:`$(...)`、反引号在任何位置(含赋值前缀)都展开后判定;无法展开时默认拒绝。
- 解释器识别放宽:带版本号的解释器名、组合标志(`-lc` 视为内联代码)。
- 敏感路径判定收紧到"文件名形态":裸单词不再误杀,保留 `.env` / `.ssh` / `id_rsa` 等真实目标;放行 `.env.example` 类模板。
- 文件边界下移到 `grep`/`find`/`ls`(只读:界内放行、界外放行并警告、敏感路径拒绝)。
- 警告通道打通:越界读的提示进入模型可见的工具结果。

**验收**:E1 五类绕过全部 `ask`/`deny`;E2 三类误杀全部 `allow`;E3 三个越界入口至少带警告;越界读结果文本含提示;新增回归用例覆盖每条绕过。

### 4.2 context-accounting-fidelity

- bash 合并输出统一上限:stdout/stderr 合并后再按 `effective_output_bytes` 截断一次,标记 `merged_budget`,元数据同步;删除死常量。
- 中英混合 token 估算:CJK 按约 1 token/字、其余按 4 字符/token;预算快照与压缩共用同一估算函数。

**验收**:E5 场景合并结果 ≤ 上限且 `truncated_by="merged_budget"`;E6 中文估算误差 ≤ 20%;纯英文结果与现状一致(允许 1 token 误差);压缩切点测试全绿。

### 4.3 session-index-incremental

- 调整 `_append` 顺序:先读有效索引(此时指纹与文件一致)→ 应用记录 → 写 JSONL → 用新指纹写索引。
- 冷启动(无索引)仍回源重建一次,保持"索引可重建、JSONL 唯一真相"。

**验收**:E7 场景 1000 次 append 总耗时 ≤ 1s(当前约 7s);新增"追加后索引仍有效"回归;并发追加与索引损坏场景不回归。

## 5. v0.6 交付状态(2026-10-22)

三项变更已实现、验证并归档(OpenSpec `openspec/changes/archive/2026-10-22-*`),主规格已同步。

| 变更 | 归档目录 | 主规格 | 结果 |
|---|---|---|---|
| security-classification-hardening | `2026-10-22-security-classification-hardening` | `tools` | 21 条新回归用例覆盖绕过/误杀/边界/警告 |
| context-accounting-fidelity | `2026-10-22-context-accounting-fidelity` | `tools` `context-budget` | 合并输出 ≤ 统一上限;CJK 按字计价 |
| session-index-incremental | `2026-10-22-session-index-incremental` | `sessions` | 1000 次追加 0.37s(原约 7s) |

实测复验(同一脚本,修复后):

| 证据 | 修复前 | 修复后 |
|---|---|---|
| E1 `timeout 5 rm -rf ~` | allow | **deny** |
| E1 `nice -n 5 rm -rf ~/d` | allow | **ask** |
| E1 `env -i rm -rf /tmp/x` | allow | **ask** |
| E1 `bash -lc 'rm -rf ~'` | allow | **deny** |
| E1 `foo=$(rm -rf ~)` | allow | **deny** |
| E2 `echo secret` / `grep -r SECRET src` / `cat .env.example` | deny | **allow** |
| E3 `grep ~/.ssh` / `find /` / `ls ~` | allow(无警告) | **deny** / **allow+warning** / **allow+warning** |
| E5 40KB+40KB 合并输出 | 60073 字符 | **≤30000 字节,`truncated_by=merged_budget`** |
| E6 50 个中文字符 | 12 tokens | **42 tokens** |
| E7 1000 次 append | ≈7s | **0.37s** |

附加修正:工具结果裁剪改为按**估算 token** 二分收敛(原按 `allocation * 4` 字符数,对 CJK 失效);越界警告经 `ToolDecision.warning` 进入模型可见的工具结果文本。

验证命令与结果:

```bash
uv run pytest -q                                    # 1759 passed
uv run pytest -m "unit or contract" -q              # 1610 passed
uv run pytest -m "integration or e2e or platform or compatibility" -q   # 161 passed
uv run ruff check src tests scripts                 # All checks passed
uv run ruff format --check src tests scripts        # 515 files already formatted
uv run python scripts/scale_scan.py                 # 通过(300 行 / 80 行)
uv run python scripts/type_scan.py                  # 类型棘轮通过
openspec validate --specs                           # 24 passed
```

## 6. 后续版本(不在 v0.6)

| 版本 | 主题 | 关键点 | 验收 |
|---|---|---|---|
| v0.7 | 执行控制 | `steer` 接入 TUI;暴露 `followup`;后台作业(`detach` + job 查询/取消);headless `--json` 事件流 | 运行中可注入 steer;长命令不阻塞输入;事件 NDJSON 带 schema 版本 |
| v0.8 | 沙箱 + 程序化工具 | 三档沙箱(`read-only`/`workspace-write`/`full`);`run_code` 程序化工具编排 | 沙箱逃逸用例 0;同一任务模型往返次数下降 ≥50% |
| v0.9 | 子 Agent 演进 | 子会话续跑 → 有界并行只读 → worktree 写隔离与父级裁决 | 子会话可追问;并行结果可裁决;写冲突有明确失败语义 |
| v1.0 | 对外接口 | 发行元数据(description/license/authors/urls)、SDK 入口、真实 provider 可选冒烟 | 干净环境可装可跑;SDK 有稳定示例 |

不做的方向:账号绑定与商业插件市场(与"可替换、可嵌入"定位冲突)、费用估算(单价漂移且非用户当前痛点)。

## 7. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| 分类器收紧导致误报上升 | 模型正常操作被拒,体验退化 | 误杀回归用例与绕过用例同等强制;敏感路径按"文件名形态"匹配而非子串 |
| 中文估算调整抬高输入估算 | 小窗口会话更早触发压缩 | 仅改估算口径,不改阈值;用真实 usage 校准留作 v0.7 |
| 索引增量写入引入并发竞争 | 索引与 JSONL 不一致 | 全程持有路径锁;索引失效时回源重建;并发追加用例回归 |
| 合并输出截断隐藏关键 stderr | 诊断信息丢失 | 保留末尾(错误通常在末尾)、保留 `stderr_summary` 与总量事实 |

## 8. 与既有文档的关系

- 架构事实以 [architecture.md](./architecture.md) 为准;本文只描述 v0.6 的范围与验收。
- 三项变更分别对应 OpenSpec change:`security-classification-hardening`、`context-accounting-fidelity`、`session-index-incremental`。
- 完成后同步更新 `docs/iteration/v0.6.md`、`CHANGELOG.md` 与相关主规格。

---

## 附录：事后状态（2026-10-24）

E1～E7 已全部修复并通过回归（见 `docs/iteration/v0.6.md`）。§3 中标为"结构性代差"的部分也已分两批补齐或明确收口：

| 原结论 | 当前状态 |
|---|---|
| 安全只有执行前分类，无执行时隔离 | **已交付**三档沙箱（`read-only` / `workspace-write` / `danger-full-access`，macOS Seatbelt / Linux bwrap，受限策略无后端 fail-closed） |
| 子 Agent 串行只读、不可写 | **已交付**有界并发槽位（默认仍串行）与 `implement` 受限可写 profile（禁 `delegate`/MCP） |
| 工具调用 = 一次函数调用 = 一次模型往返 | 未变；程序化工具编排（`run_code` 形态）仍在后续评估 |
| `steer`/`followup` 未接通 UI、无后台作业 | 未变，仍在后续评估 |
| 事件仅内部消费、无对外导出 | 未变；离线评测（`python -m evals`）已补齐行为回归，但不等于事件导出 |
| 无插件机制 | **已交付 v1**（仅贡献工具、目录即信任、`ext__` 命名空间、默认需确认） |
| 工作区无回退能力 | **已交付**写前 checkpoint 与 `tenon undo`（LIFO、有界、不阻塞写入） |

Web UI 明确不规划；跨进程恢复、长期记忆与费用估算仍不在范围内。
