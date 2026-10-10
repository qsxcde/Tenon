"""扫描生产代码的文件与函数规模，把 AGENTS.md 的规模约束变成可执行门禁。

历史版本只扫描 ``src/codeagent/app``，因此 ``tools/`` 与 ``ai/`` 的超限文件从未
被任何自动检查发现。这里改为扫描整个生产包，并由
``tests/contracts/test_scale_limits.py`` 纳入 ``unit or contract`` 质量门禁。
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_LINES = 300
MAX_FUNCTION_LINES = 80

PRODUCTION_ROOT = Path(__file__).resolve().parents[1] / "src" / "codeagent"

# 兼容外观在迁移收口后不再允许；确需豁免时必须逐项登记书面理由。
COMPATIBILITY_EXCEPTIONS: dict[str, str] = {}


@dataclass(frozen=True)
class ScaleViolation:
    path: Path
    kind: str
    actual: int
    limit: int
    symbol: str | None = None

    def format(self) -> str:
        location = f"::{self.symbol}" if self.symbol else ""
        return f"{self.path}{location}: {self.kind} {self.actual} > {self.limit}"


def _function_violations(path: Path, tree: ast.Module) -> list[ScaleViolation]:
    violations: list[ScaleViolation] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end_lineno = getattr(node, "end_lineno", node.lineno)
        actual = end_lineno - node.lineno + 1
        if actual > MAX_FUNCTION_LINES:
            violations.append(
                ScaleViolation(path, "函数行数", actual, MAX_FUNCTION_LINES, node.name)
            )
    return violations


def scan_file(path: Path, relative: str) -> list[ScaleViolation]:
    """Return the file- and function-size violations for one production module."""
    if relative in COMPATIBILITY_EXCEPTIONS:
        return []
    violations: list[ScaleViolation] = []
    source = path.read_text(encoding="utf-8")
    line_count = len(source.splitlines())
    if line_count > MAX_FILE_LINES:
        violations.append(ScaleViolation(path, "文件行数", line_count, MAX_FILE_LINES))
    violations.extend(_function_violations(path, ast.parse(source, filename=str(path))))
    return violations


def scan_root(root: Path = PRODUCTION_ROOT) -> list[ScaleViolation]:
    """Return every size violation under one production directory."""
    violations: list[ScaleViolation] = []
    for path in sorted(root.rglob("*.py")):
        violations.extend(scan_file(path, path.relative_to(root).as_posix()))
    return violations


def main() -> int:
    violations = scan_root()
    if violations:
        print("\n".join(violation.format() for violation in violations))
        return 1
    print(f"生产代码规模检查通过（{MAX_FILE_LINES} 行文件 / {MAX_FUNCTION_LINES} 行函数）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
