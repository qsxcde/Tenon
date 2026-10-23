## Why

安全分类器目前是"字面量模式匹配",实测存在可被一个前缀绕过的危险命令,同时误杀正常的安全审查动作:

- `timeout 5 rm -rf ~`、`nice -n 5 rm -rf ~/d`、`env -i rm -rf /tmp/x`、`bash -lc 'rm -rf ~'`、`foo=$(rm -rf ~)` 全部返回 `allow`;
- `echo secret`、`grep -r SECRET src`、`read .env.example` 全部返回 `deny`;
- `grep {"path": "~/.ssh"}`、`find "/"`、`ls "~"` 全部返回 `allow`(文件边界只覆盖 read/write/edit)。

"安全确认环"是项目对外承诺的能力之一,上述三类偏差分别代表**漏报**(危险命令放行)、**误报**(正常动作被拒)和**边界缺口**(只读搜索工具无边界)。同时越界读取的 `warning` 在运行适配层被丢弃,模型完全看不到"你越界了"。

## What Changes

- 包装器语义解析:识别 `timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec` 及其参数(含 `VAR=value` 前缀),定位真正被执行的命令再判定。
- 命令替换递归展开:`$(...)`、反引号,无论出现在命令首部、参数位置还是 `foo=$(...)` 赋值内,都先展开再判定;无法完成分词或展开时默认拒绝。
- 解释器识别放宽:带版本号的解释器名(`python3.12`)、组合标志(`-lc` 视为内联代码)进入 ask 档。
- 敏感路径判定收紧为"文件名形态":裸单词不再命中;保留 `.env`、`.ssh/`、`id_rsa`、`*.pem` 等真实目标;放行 `.env.example` / `.env.sample` / `.env.template` 等模板文件。
- 文件边界下移到只读搜索工具:`grep` / `find` / `ls` 与 read 采用同一分类:界内放行、界外放行并携带警告、敏感路径拒绝。
- 警告通道打通:越界读的警告进入模型可见的工具结果文本,而不是只停留在决策对象里。

## Capabilities

### New Capabilities

### Modified Capabilities

- `tools`: 收紧 bash 包装器与命令替换判定、修正敏感路径误报、把文件访问边界扩展到只读搜索工具、把越界警告送达模型。

## Impact

- 影响 `src/codeagent/tools/security/`(`bash_rules`、`ask_rules`、`filesystem`、`classifier`)与 `core/contracts/ports.py`、`core/orchestration/tool_call.py`、`session/runtime/execution.py` 的警告传递路径。
- 不改动工具参数 schema、会话持久化格式、provider 协议和事件类型集合。
- 新增纯函数回归测试(绕过 8 例、误杀 5 例、边界 3 例、警告送达 1 例);不需要网络、密钥或真实子进程。
