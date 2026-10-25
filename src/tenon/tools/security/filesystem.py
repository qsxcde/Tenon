"""文件工具的工作区边界与敏感路径策略。

敏感路径判定分两层,避免"任意 token 子串搜索"造成的误杀:

- **明确目标**:`.env`、`.ssh/`、`id_rsa`、`*.pem` 等,即使作为裸 token 也拒绝;
- **凭据文件名**:`credentials.json` / `secrets.yaml` 等,只在 token 具有文件名形态
  (含分隔符、以 `.` 开头或带已知扩展名)时生效,因此 `echo secret` 不再被拒。

文件访问边界对只读工具(read / grep / find / ls)统一为:界内放行、界外放行并警告、
敏感路径拒绝;写与编辑越界仍需确认。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from tenon.tools.security.decision import ALLOW, ASK, DENY, SecurityDecision

#: 明确的敏感目录/文件名:裸 token 同样拒绝。
_SECRET_TARGET_RE = re.compile(
    r"(^|[/\\])(?:\.env|\.tenon|\.codeagent|\.ssh|\.aws|\.gnupg)(?:$|[/\\])|"
    r"(^|[/\\])(?:\.git-credentials|\.netrc|\.npmrc|\.pypirc)$|"
    r"(^|[/\\])id_(?:rsa|dsa|ecdsa|ed25519)(?:$|[.])|"
    r"[^/\\]+\.(?:pem|key|pfx)$",
    re.IGNORECASE,
)
#: 凭据类文件名:只在 token 具有路径/文件名形态时生效。
_CREDENTIAL_NAME_RE = re.compile(
    r"(^|[/\\])(?:credentials|secrets?|tokens?)(?:\.(?:json|ya?ml|toml|ini|cfg|conf))?$",
    re.IGNORECASE,
)
#: 凭据类文件名的裸文件名形态(带已知扩展名)。
_CREDENTIAL_FILENAME_RE = re.compile(r"^[^/\\]+\.(?:json|ya?ml|toml|ini|cfg|conf)$", re.IGNORECASE)
#: 公认可读的模板文件:不含真实密钥,不应触发凭据拒绝。
_SECRET_TEMPLATES = frozenset(
    {".env.example", ".env.sample", ".env.template", ".env.dist", ".env.defaults"}
)

_BOUNDED_TOOLS = ("read", "write", "edit")
_SEARCH_TOOLS = ("grep", "find", "ls")
_READ_TOOLS = ("read", "grep", "find", "ls")
_WRITE_TOOLS = ("write", "edit")


def _looks_like_path(token: str) -> bool:
    """Return whether a token names a file rather than an ordinary word."""
    return (
        "/" in token
        or "\\" in token
        or token.startswith(".")
        or bool(_CREDENTIAL_FILENAME_RE.match(token))
    )


def _is_secret_target(token: str) -> bool:
    normalized = token.replace("\\", "/")
    basename = normalized.rsplit("/", 1)[-1].lower()
    if basename in _SECRET_TEMPLATES:
        return False
    if _SECRET_TARGET_RE.search(normalized):
        return True
    return _looks_like_path(normalized) and bool(_CREDENTIAL_NAME_RE.search(normalized))


def _secret_path_hit(segments: list[list[str]]) -> str | None:
    for segment in segments:
        for token in segment:
            if _is_secret_target(str(token)):
                return f"命令涉及敏感凭据路径,已拒绝读取或写入: {token}"
    return None


def within_workspace(path: str | Path, workspace: str | Path) -> str:
    """按 realpath/inode 判断路径是否位于工作区内。"""
    target = Path(path)
    root = Path(workspace)
    try:
        real_target = target.resolve()
        real_root = root.resolve()
    except OSError:
        return "unresolvable"
    try:
        if target.exists():
            cur = real_target
            while True:
                try:
                    if os.path.samefile(cur, root):
                        return "inside"
                except OSError:
                    pass
                if cur.parent == cur:
                    break
                cur = cur.parent
    except OSError:
        pass
    norm = os.path.normcase(str(real_target))
    norm_root = os.path.normcase(str(real_root))
    if norm == norm_root or norm.startswith(norm_root + os.sep):
        return "inside"
    return "outside"


def classify_file(tool_name: str, path: str | Path, workspace: str | Path) -> SecurityDecision:
    """只读越界放行并警告;写/编辑越界需确认;敏感路径硬拒绝。"""
    raw_path = Path(path).expanduser()
    try:
        resolved_path = raw_path.resolve()
    except OSError:
        resolved_path = raw_path
    secret_hit = _secret_path_hit([[str(raw_path), str(resolved_path)]])
    if secret_hit is not None:
        return SecurityDecision(DENY, secret_hit)
    status = within_workspace(path, workspace)
    if status == "inside":
        return SecurityDecision(ALLOW)
    if tool_name in _READ_TOOLS:
        return SecurityDecision(ALLOW, f"越界读取: {path}", warning=True)
    if status == "unresolvable":
        return SecurityDecision(ASK, f"路径无法解析,按越界处理: {path}")
    return SecurityDecision(ASK, f"越出工作区: {path}")


__all__ = [
    "classify_file",
    "SECRET_TEMPLATES",
    "within_workspace",
]
