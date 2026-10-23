## Context

当前判定链是 `classify_tool` → `classify_bash` / `classify_file` → `SecurityDecision(action, reason, warning)`。`bash_rules._dangerous_intent` 负责静态危险意图,其中 `_effective_command_index` 用一张跳过表定位"真正的命令";`ask_rules` 的每条规则只看 `segment[0]`;`_strip_substitution` 只认以 `$` 开头且整体闭合的 token;解释器名单是精确集合。文件边界由 `_BOUNDED_TOOLS = ("read", "write", "edit")` 控制。

运行期 `before_tool_call` 只读 `decision.action`,把 `PolicyDecision.warning` 丢弃,因此"越界读放行并提示"只实现了一半。

## Goals / Non-Goals

**Goals:**

- 让"危险命令黑名单"对常见 POSIX 包装形式成立,且无法被单一前缀绕过。
- 让正常的安全审查动作(搜索 `secret` 关键字、读 `.env.example`)不再被误杀。
- 让只读搜索工具与 read 共享同一文件边界语义。
- 让越界警告对模型可见。

**Non-Goals:**

- 不实现操作系统级沙箱(容器、seatbelt、bubblewrap);那是 v0.8。
- 不引入 AST 级 shell 解析器或第三方 shell 语法库。
- 不改动 ask/deny/allow 三档语义与 `ApprovalPolicy` 端口形状。
- 不为 MCP 工具新增边界策略。

## Decisions

### 1. 包装器改为"语义跳过"而非"名单跳过"

原实现用 `("sudo", "env", "time", "nohup", "command")` 这张表跳过首 token,既漏 `timeout/nice/xargs/stdbuf/builtin/exec`,也在跳过 `env` 后没跳过它的 `-i` 参数。

改为逐个包装器消费其**参数与操作数**,直到遇到第一个"非选项、非赋值"的 token:

- `VAR=value` 前缀直接跳过;
- `env` 跳过 `-i/-u/--` 及其参数后继续;
- `timeout` 跳过选项与时长操作数后继续;
- `nice`/`stdbuf` 跳过选项与其参数;`xargs` 跳过选项;
- `command`/`builtin`/`exec`/`nohup`/`time` 跳过自身选项;
- 跳过后仍无法确定命令(参数耗尽)则**保守拒绝**。

备选方案是引入 `bashlex` 之类的 AST 解析器,但那会新增依赖、且仍需对动态构造失败兜底,与"零新依赖 + 失败即拒绝"的取舍不符。

### 2. 命令替换在任何位置递归展开

`shlex` 把 `foo=$(rm -rf ~)` 切成 `['foo=$', '(', 'rm', '-rf', '~', ')']`,`_strip_substitution` 只认整 token 的 `$(...)`。改为在 token 级别识别 `$(`/```(任意前缀)与 `${` 展开:把括号内的内容抽出来递归判定;反引号同理;无法闭合或展开失败一律拒绝。

关键取舍:**嵌套深度上限保持 5**,超过即拒绝,避免构造深嵌套导致判定退化。

### 3. 敏感路径按"文件名形态"匹配

`_SECRET_PATH_RE` 中 `(?:credentials|secrets?|tokens?)(?:$|\.(?:json|...))` 会对每个 token 做 `search`,`echo secret` 的 `secret` 命中 `$` 锚点而整条被拒。

改为:只有当 token 形如路径(含 `/` 或 `\`,或以 `.` 开头且含扩展名)时才应用"凭据类文件名"分支;`.env` / `.ssh` / `id_rsa` / `*.pem` 等**明确目标**分支保持对裸文件的匹配。同时为 `.env.example`、`.env.sample`、`.env.template`、`.env.dist` 增加显式放行。

### 4. 只读搜索工具共用文件边界

把 `grep` / `find` / `ls` 加入边界判定,但语义与 read 一致:**界内 allow、界外 allow+warning、敏感路径 deny**。这样既不改变"本地单用户、模型误操作"的威胁模型,也堵住 `grep ~/.ssh/id_rsa` 绕过 read 的洞。

路径参数名不同(`file_path` vs `path`),由 `classify_tool` 统一提取,`grep` 缺省 `.`。

### 5. 警告通过结果文本送达模型

运行期 `before_tool_call` 允许执行时,若 `decision.warning` 为真,把 `decision.reason` 作为**前缀提示**注入工具结果文本(例如 `[安全提示] 越界读取: ...`),并保留原有 metadata。这样不新增事件类型、不改 `ToolResult` 形状,模型看到的是同一条工具结果里的一行提示。

## Risks / Trade-offs

- **[收紧判定抬升误报]** → 误杀用例与绕过用例同等强制;`.env.example` 等模板显式放行;规则仅覆盖"文件名形态"。
- **[语义跳过可能跳过过多参数]** → 包装器跳过后仍要求"第一个非选项 token 必须是已知命令形态",否则拒绝而非放行。
- **[警告前缀污染工具输出]** → 前缀单行、固定格式、可被下游按行剥离;结构化 metadata 不受影响。
- **[grep/find/ls 边界引入额外 stat]** → 复用已有 `within_workspace`,只在分类阶段执行一次,不影响工具执行路径。
