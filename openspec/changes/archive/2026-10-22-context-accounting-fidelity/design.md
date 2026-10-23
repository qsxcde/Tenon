## Context

`BashTool._format_result` 用 `_stream_stats` 读取每个流各自的 `total/shown/truncated` 事实,拼成 `header + stdout + stderr` 后直接返回 `GovernedText`,合并结果没有二次上限。`ToolResourceLimits.effective_output_bytes` 已经是"输出上限 + 物化内存上限"的较小值,是天然的合并上限来源。

`core/context/budget.py` 的 `_estimate_text_tokens` 与 `session/compaction/policy.py` 的 `estimate_tokens` 都使用 `len // 4`。两者各自独立实现,口径相同但位置分散。

## Goals / Non-Goals

**Goals:**

- 单次 bash 工具结果对模型可见的字符数不超过配置的有效上限。
- token 估算对中文接近真实值,对英文保持现状。
- 预算与压缩使用同一估算函数,避免两处漂移。

**Non-Goals:**

- 不引入 provider tokenizer 或第三方分词库。
- 不实现基于真实 usage 的自校准(留给后续版本)。
- 不改动压缩触发比例、preflight 阈值与工具资源默认值。
- 不改变 `GovernedText` 与 `ToolOutputMetadata` 的字段集合。

## Decisions

### 1. 合并后统一截断,保留末尾

在拼接完成后,以 `effective_output_bytes` 再次调用 `truncate_tail`(错误信息通常在末尾),若发生截断则:

- `completeness = "truncated"`(若此前是 `incomplete/timeout` 则保持不变);
- `truncated_by = "merged_budget"`;
- `total_bytes` 保持合并前的真实总量,`shown_bytes`/`shown_lines` 更新为最终值;
- 在正文末尾追加既有截断标记。

选择"保留末尾"而不是"保留开头",与 bash 现有 `output_direction="tail"` 一致,避免同时引入两种截断方向。

### 2. CJK 与 ASCII 分权重估算

新增单一实现:`sum(1 cjk_char) + ceil(ascii_chars / 4)`,下限 1。CJK 判定用码点区间(Han、Hiragana、Katakana、Hangul、全角标点),不依赖 `unicodedata` 之外的标准库。`core/context/budget.py` 与 `session/compaction/policy.py` 都改为调用它。

备选方案是按 `bytes/4` 估算(中文 UTF-8 三字节 → 0.75 token/字),但那会高估标点与常见双字词,且与英文口径不一致;码点加权更可控。

### 3. 保守方向

CJK 权重取 1.0 而非 1.5,理由是常见中文约 1.2~1.6 字/token,取 1.0 仍偏保守但比现状精确 4 倍;估算偏高会提前触发压缩,属于安全方向的失败。

## Risks / Trade-offs

- **[估算偏高导致更早压缩]** → 压缩本身有 `min_recent_turns` 与目标预算保护,提前压缩只影响上下文长度不影响正确性。
- **[合并截断隐藏 stdout 关键内容]** → 保留末尾 + `stderr_summary` + 真实总量事实;模型仍可再次执行更精确的命令。
- **[两处估算实现合并]** → 由测试同时断言预算快照与压缩切点使用同一函数,防止再次分叉。
