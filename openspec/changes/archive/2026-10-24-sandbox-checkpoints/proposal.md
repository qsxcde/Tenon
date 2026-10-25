# 沙箱执行与文件级 Checkpoint

## Why

bash 目前直接以宿主进程执行,安全只依赖静态命令分类;工作区写入没有可回退的文件级快照,误改只能靠版本控制或人工恢复。生态实践(harness 的三档沙箱策略)表明"能选的进程边界 + 可撤销写入"是运行期安全的基础能力。

## What Changes

- 新增三档沙箱策略:`read-only` / `workspace-write` / `danger-full-access`(默认,保持原行为)。macOS 使用 `sandbox-exec`(Seatbelt)限制文件写;Linux 使用 `bwrap` 绑定只读根与可写工作区;受限策略无后端时 **fail-closed**(明确诊断、拒绝执行),不静默降级。
- `ProcessRequest` 增加 `argv_prefix`,沙箱后端以独立 argv 元素注入(不经过 shell 拼接)。
- 新增写前 checkpoint:`write` / `edit` 在路径锁内、写入前保存原文快照到 `~/.tenon/checkpoints/`;`tenon undo` 支持 `--list` / `--dry-run` / LIFO 恢复;条目数有上限并淘汰最旧。

## Capabilities

### Modified Capabilities

- `tools`: 新增「命令执行沙箱策略」与「写前 checkpoint 与恢复」需求。

## Impact

- 影响 `tools/execution/sandbox.py`(新增)、`tools/execution/process.py`、`tools/atomic/bash.py`、`tools/atomic/{write,edit}.py`、`tools/shared/checkpoints.py`(新增)、`tools/registry.py`、`app/config.py`、`app/main.py`。
- 默认策略与默认行为不变;受限策略需要用户显式开启。
- checkpoint 不进入会话 JSONL,不改变提交语义;测试全部离线。
