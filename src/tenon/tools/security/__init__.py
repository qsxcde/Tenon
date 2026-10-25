"""工具执行安全策略公共入口。"""

from tenon.tools.security.bash_rules import DANGEROUS_PATTERNS
from tenon.tools.security.classifier import DEFAULT_ALLOWLIST, classify_bash, classify_tool
from tenon.tools.security.decision import ALLOW, ASK, DENY, SecurityDecision
from tenon.tools.security.filesystem import classify_file, within_workspace
from tenon.tools.security.mcp import classify_mcp

__all__ = [
    "ALLOW",
    "ASK",
    "DENY",
    "DANGEROUS_PATTERNS",
    "SecurityDecision",
    "DEFAULT_ALLOWLIST",
    "classify_bash",
    "classify_file",
    "classify_mcp",
    "classify_tool",
    "within_workspace",
]
