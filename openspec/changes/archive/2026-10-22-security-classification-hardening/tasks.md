## 1. 分类器语义解析

- [x] 1.1 用语义跳过替换 `_effective_command_index` 的固定名单:支持 `timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec` 及其选项与操作数,并保留 `VAR=value` 前缀跳过。
- [x] 1.2 命令替换在任何位置递归展开:`$(...)`、反引号、`${...}`;赋值前缀内同样展开;无法展开或嵌套超限时拒绝。
- [x] 1.3 解释器识别放宽:带版本号的名字(`python3.12`、`node18` 形态)与组合标志(`-lc`、`-ec`)命中内联代码规则。

## 2. 误报与边界修正

- [x] 2.1 敏感路径判定改为"路径形态 + 明确目标";裸单词不再命中;放行 `.env.example` / `.env.sample` / `.env.template` / `.env.dist`。
- [x] 2.2 只读搜索工具(`grep`/`find`/`ls`)接入文件边界:界内 allow、界外 allow+warning、敏感路径 deny;`classify_tool` 统一提取 `file_path`/`path`。
- [x] 2.3 越界警告送达模型:允许执行的调用在结果文本前置安全提示行,保留原有 metadata。

## 3. 回归与验收

- [x] 3.1 新增绕过回归:五类包装/替换形式各至少一例,断言 `ask` 或 `deny`。
- [x] 3.2 新增误杀回归:`echo secret`、`grep -r SECRET src`、`read .env.example` 断言 allow 或非 deny。
- [x] 3.3 新增边界回归:`grep ~/.ssh`、`find /`、`ls ~` 断言带 warning 或 deny;越界读结果文本包含提示。
- [x] 3.4 运行 `tests/tools/test_security.py`、`tests/tools/atomic`、`tests/core` 与 `tests/session` 相关窄测试,确认无回归。

## 4. 文档与规格

- [x] 4.1 更新 `openspec/specs/tools/spec.md` 的「bash 命令执行」「文件访问边界」要求与场景。
- [x] 4.2 更新 `docs/design/roadmap-v0.6.md` 的验收状态与 `CHANGELOG.md`。
- [x] 4.3 运行 `ruff check`、`ruff format --check`、`scale_scan`、`type_scan` 与 `openspec validate`。
