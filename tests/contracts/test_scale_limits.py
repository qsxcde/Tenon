"""规模门禁:AGENTS.md 的 300 行文件 / 80 行函数约束必须覆盖全部生产层。

历史 ``scale_scan`` 只扫描 ``app/``,并由三个各管一层的测试拼出覆盖面,导致
``tools/`` 与 ``ai/`` 的超限文件从未被任何自动检查发现。本测试把覆盖面收敛为
"整个生产包",并保留豁免清单的书面理由校验与门禁自身的回归校验。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.scale_scan import (
    COMPATIBILITY_EXCEPTIONS,
    MAX_FILE_LINES,
    MAX_FUNCTION_LINES,
    PRODUCTION_ROOT,
    scan_root,
)

pytestmark = pytest.mark.contract


def test_production_tree_has_no_size_violations() -> None:
    violations = scan_root()

    assert not violations, "生产代码规模超限:\n" + "\n".join(
        violation.format() for violation in violations
    )


def test_scale_limits_match_the_repository_contract() -> None:
    assert MAX_FILE_LINES == 300
    assert MAX_FUNCTION_LINES == 80


def test_gate_spans_every_layer_not_only_the_application_layer() -> None:
    assert PRODUCTION_ROOT.name == "tenon"
    for layer in ("app", "core", "session", "ai", "tools"):
        assert (PRODUCTION_ROOT / layer).is_dir(), f"生产层 {layer} 缺失"


def test_scan_detects_an_oversized_module(tmp_path: Path) -> None:
    oversized = tmp_path / "tools" / "bloated.py"
    oversized.parent.mkdir()
    oversized.write_text("# comment\n" * (MAX_FILE_LINES + 1), encoding="utf-8")

    violations = scan_root(tmp_path)

    assert [violation.kind for violation in violations] == ["文件行数"]
    assert violations[0].limit == MAX_FILE_LINES


def test_scan_detects_an_oversized_function(tmp_path: Path) -> None:
    body = "\n".join(f"    value = {index}" for index in range(MAX_FUNCTION_LINES))
    module = tmp_path / "long_func.py"
    module.write_text(f"def build():\n{body}\n    return value\n", encoding="utf-8")

    violations = scan_root(tmp_path)

    assert [violation.symbol for violation in violations] == ["build"]


def test_every_exception_carries_a_written_justification() -> None:
    for relative, reason in COMPATIBILITY_EXCEPTIONS.items():
        assert relative.endswith(".py")
        assert isinstance(reason, str) and reason.strip(), f"规模豁免 {relative} 缺少理由"
