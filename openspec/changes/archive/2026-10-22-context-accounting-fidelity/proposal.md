## Why

上下文治理的结构完整(预算快照、preflight 四态、自动压缩、工具结果裁剪),但两个估算口径与结果上限存在可实测的偏差:

- **bash 合并输出无上限**:stdout 与 stderr 各自按 30KB 截断,合并后模型可见约 60KB;单次工具结果即可吃掉大半预算;`MAX_OUTPUT_CHARS` 常量定义后从未使用。
- **中文 token 四倍低估**:50 个中文字符估算为 12 tokens(实际约 50),而纯英文估算接近准确。这使 preflight 的 `over_limit` 在小窗口中文会话中判不出来,自动压缩的目标预算也随之失真。

两个问题都直接削弱"请求前预算门禁"和"自动压缩不溢出"这两条既有承诺。

## What Changes

- bash 结果在 stdout/stderr 合并后统一再截断一次,上限为工具的有效输出字节上限;截断时标记 `merged_budget`,同步更新 `shown_bytes`/`shown_lines`/`completeness` 与事件 metadata;删除未使用的 `MAX_OUTPUT_CHARS` 常量。
- token 估算改为中英混合口径:CJK 字符按约 1 token/字,其余字符按 4 字符/token;预算快照与压缩切点共用同一估算实现。
- 保持纯英文输入与现有行为一致(允许 1 token 级别差异),不改变预算阈值、压缩触发比例或任何持久化格式。

## Capabilities

### New Capabilities

### Modified Capabilities

- `tools`: bash 合并输出受统一上限约束并标记真实截断原因。
- `context-budget`: 预算与压缩使用中英混合 token 估算,估算口径在两类消费方之间一致。

## Impact

- 影响 `src/tenon/tools/atomic/bash.py`、`src/tenon/core/context/budget.py`、`src/tenon/session/compaction/policy.py`。
- 不改动工具参数 schema、provider 协议、事件类型集合与 JSONL 格式。
- 新增纯函数与工具级回归测试;不需要网络或真实 provider。
