"""有序工具钩子链执行(pre:通知/改参/门禁;post:变换/保留)。

链语义(design tool-waterfall):
- pre 链按注册顺序执行,前一钩子的输出是后一钩子与执行的输入;
  返回 None=通知继续、ToolCall=改参继续、ToolDecision.block=门禁短路、
  ToolDecision.allow(可附 warning)=放行并按序累积警告;
- 门禁短路后不执行工具、不跑 post 链;
- post 链按顺序执行,返回 None 保留当前结果,返回 ToolResult 则替换并传给下一钩子;
- 非法返回类型抛出 TypeError(fail-closed:不得把坏钩子静默当成放行)。
"""

from __future__ import annotations

from dataclasses import dataclass

from codeagent.core.context.contracts import AfterToolCall, BeforeToolCall
from codeagent.core.contracts.messages import ToolCall, ToolResult
from codeagent.core.contracts.ports import ToolDecision
from codeagent.core.support.awaiting import await_if_needed


@dataclass(frozen=True)
class PreChainOutcome:
    """pre 链执行结果:门禁原因(非 None = 短路)、改参后的调用、累积警告。"""

    blocked_reason: str | None
    call: ToolCall
    warnings: tuple[str, ...]


async def run_pre_chain(
    hooks: tuple[BeforeToolCall, ...],
    call: ToolCall,
    context: object,
) -> PreChainOutcome:
    """顺序执行 pre 链;门禁短路或返回改参后的调用与累积警告。"""
    warnings: list[str] = []
    for hook in hooks:
        outcome = await await_if_needed(hook(call, context))
        if outcome is None:
            continue
        if isinstance(outcome, ToolCall):
            call = outcome
            continue
        if isinstance(outcome, ToolDecision):
            if outcome.action != "allow":
                return PreChainOutcome(outcome.reason, call, ())
            if outcome.warning and outcome.reason:
                warnings.append(outcome.reason)
            continue
        raise TypeError(
            f"before_tool_calls 钩子返回值类型非法: {type(outcome).__name__}"
            "(期望 ToolCall | ToolDecision | None)"
        )
    return PreChainOutcome(None, call, tuple(warnings))


async def run_post_chain(
    hooks: tuple[AfterToolCall, ...],
    call: ToolCall,
    result: ToolResult,
    context: object,
) -> ToolResult:
    """顺序执行 post 链;返回链尾结果(逐钩子可替换或保留)。"""
    for hook in hooks:
        updated = await await_if_needed(hook(call, result, context))
        if updated is not None:
            if not isinstance(updated, ToolResult):
                raise TypeError(
                    f"after_tool_calls 钩子返回值类型非法: {type(updated).__name__}"
                    "(期望 ToolResult | None)"
                )
            result = updated
    return result


__all__ = ["PreChainOutcome", "run_post_chain", "run_pre_chain"]
