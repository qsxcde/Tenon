"""执行前安全策略的组合根适配。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tenon.core.contracts.ports import ApprovalOutcome, ApprovalResult, PolicyDecision


def _create_policy(cfg: Any = None, approval_mode: str = "deny") -> Any:
    """按形态装配执行前安全策略。"""
    from tenon.app.config import CONFIG_DIR
    from tenon.tools.mcp.permissions import parse_mcp_permissions
    from tenon.tools.plugins.permissions import parse_extension_permissions
    from tenon.tools.security import classify_tool

    workspace = getattr(cfg, "cwd", None) if cfg is not None else None
    workspace = str(Path(workspace or Path.cwd()).expanduser().resolve())
    mcp_rules = parse_mcp_permissions(CONFIG_DIR)
    ext_rules = parse_extension_permissions(CONFIG_DIR)

    def _target_exists(target: str) -> bool:
        path = Path(target)
        if not path.is_absolute():
            path = Path(workspace) / path
        return path.exists()

    class _Policy:
        def decide(self, tool_name: str, args: dict) -> PolicyDecision:
            decision = classify_tool(
                tool_name,
                args,
                workspace=workspace,
                cwd=workspace,
                exists=_target_exists,
                mcp_rules=mcp_rules,
                ext_rules=ext_rules,
            )
            if decision.action == "ask" and approval_mode == "deny":
                # headless 无确认通道:归因 UNAVAILABLE 并 fail-closed 拒绝
                # (ask→deny 语义保留,枚举使"为何拒绝"可诊断)。
                return ApprovalResult(
                    ApprovalOutcome.UNAVAILABLE,
                    f"未确认不得执行(headless): {decision.reason}",
                ).to_policy_decision()
            if decision.action == "ask" and approval_mode == "allow":
                return ApprovalResult(
                    ApprovalOutcome.ALLOWED_ONCE, decision.reason
                ).to_policy_decision()
            return PolicyDecision(decision.action, decision.reason, decision.warning)

    return _Policy()
