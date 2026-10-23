## MODIFIED Requirements

### Requirement: bash 命令执行

`bash` 工具 SHALL 在注入的工作目录执行 shell 命令并返回输出与退出码;默认超时 120 秒、上限 600 秒;超时或中断时 SHALL 终止整个命令进程树;输出按字节与行双上限截断并保留末尾;危险命令 SHALL 被拒绝并返回拒绝原因;敏感命令 SHALL 需用户确认,未确认不得执行;只读白名单命令 SHALL 免确认执行;grep 无匹配(退出码 1)SHALL 不视为失败;Windows 下无可用 bash 时 SHALL 返回可操作安装指引。工具 SHALL 能接收来自 Agent 执行器的取消请求;外层超时不得仅停止等待而让 bash 继续无状态运行。Windows 下无法确认终止 MSYS 派生后台孙进程时,结果 SHALL 明确标记清理不确定性。超时、输出、内存和取消清理限制 SHALL 可由组合根统一配置,且任何限制达到时 SHALL 保留原始执行状态和可诊断的限制原因。危险意图判定 SHALL 在语义层面定位真正执行的命令,不得因为前置包装器(`timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec`)或变量赋值前缀而失效;命令替换(`$(...)`、反引号)与花括号展开 SHALL 在任意位置递归展开后判定,无法可靠展开或嵌套超限时 SHALL 保守拒绝。敏感路径判定 SHALL 以路径形态与明确目标为依据,不得因为普通单词包含 `secret`/`token` 等字面量而拒绝,且 `.env.example`/`.env.sample`/`.env.template`/`.env.dist` 等模板文件 SHALL 可读。

#### Scenario: 正常执行

- **WHEN** 执行一条成功的 shell 命令
- **THEN** 返回输出、退出码 0 与耗时

#### Scenario: 命令失败返回退出码

- **WHEN** 执行一条退出码非零的命令
- **THEN** 返回非零退出码与输出,失败信息对调用方可见

#### Scenario: 危险命令被拒绝

- **WHEN** 命令命中危险模式(如 `rm -rf /`)
- **THEN** 命令不被执行,返回拒绝原因

#### Scenario: 包装器不得绕过危险判定

- **WHEN** 危险命令被 `timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec` 包裹,或带 `VAR=value` 前缀
- **THEN** 系统定位其真正执行的命令并给出与裸命令相同的拒绝或确认结论,不得返回放行

#### Scenario: 命令替换不得绕过危险判定

- **WHEN** 危险命令出现在 `$(...)`、反引号或赋值右侧的命令替换中
- **THEN** 系统递归展开后判定;展开失败或嵌套超限时保守拒绝

#### Scenario: 敏感命令需确认

- **WHEN** 命令命中敏感类别(如递归删除、推送、提权、网络下载执行、进程终止、递归权限修改)
- **THEN** 命令不被执行,等待用户确认;未确认不执行;确认后正常执行

#### Scenario: 只读白名单免确认

- **WHEN** 命令为只读白名单命令(如 ls / cat / grep / pwd / git status / git diff)
- **THEN** 命令直接执行,无需确认

#### Scenario: 安全审查动作不被误杀

- **WHEN** 命令只包含 `secret`/`token` 等字面量,或读取 `.env.example` 等模板文件
- **THEN** 命令不因字面量命中而进入拒绝档

#### Scenario: 超时终止进程树

- **WHEN** 命令超过配置的工具超时(含其派生的后台子进程)
- **THEN** 命令进程被终止并返回超时提示;派生进程树被尽力终止,清理等待不会无限阻塞,清理不确定时结果明确标注

#### Scenario: 外层取消

- **WHEN** Agent 执行器在 bash 运行期间发出取消
- **THEN** bash 进入同一进程树清理路径,按配置的清理等待时限收尾,不会只取消等待方而继续执行

#### Scenario: 输出保留末尾

- **WHEN** 命令输出超过配置的字节、行或内存物化上限
- **THEN** 返回受限的末尾部分并标记截断或内存限制,错误信息(通常在末尾)可见

#### Scenario: grep 无匹配豁免

- **WHEN** 执行以 grep 结尾的管道且 grep 无匹配
- **THEN** 退出码 1 不被视为失败,输出照常返回

#### Scenario: Windows 无 bash

- **WHEN** 在未安装 bash 的 Windows 环境执行命令
- **THEN** 返回带安装指引的可操作错误

### Requirement: 文件访问边界

read / write / edit / grep / find / ls 工具 SHALL 默认限定在注入的工作区边界内访问:边界内访问直接执行;越出边界的**只读**访问 SHALL 放行并附带越界提示(警告),且该提示 SHALL 对模型可见;越出边界的**写与编辑**访问 SHALL 需用户确认,未确认不得执行;边界判定 SHALL 防符号链接逃逸(工作区内符号链接指向边界外文件不得穿透边界);判定 SHALL 平台无关(Windows / macOS / Linux 行为一致)。敏感凭据路径 SHALL 在不区分工具种类的前提下拒绝。

#### Scenario: 边界内访问

- **WHEN** 目标路径解析后位于工作区内
- **THEN** 访问直接执行,无需确认

#### Scenario: 越界读警告放行

- **WHEN** 只读目标(read / grep / find / ls)解析后位于工作区外且不属于敏感凭据路径
- **THEN** 访问放行,工具结果包含越界提示,模型可见

#### Scenario: 只读搜索工具不得绕过边界

- **WHEN** grep / find / ls 的目标路径位于工作区外或命中敏感凭据路径
- **THEN** 系统按与 read 相同的边界结论处理,不得因为工具种类不同而静默放行

#### Scenario: 越界写需确认

- **WHEN** 写/编辑目标解析后位于工作区外
- **THEN** 访问需用户确认;未确认不执行;确认后正常执行

#### Scenario: 符号链接逃逸拦截

- **WHEN** 工作区内路径经符号链接解析后指向工作区外
- **THEN** 按越界处理(读警告 / 写需确认),不静默穿透边界
