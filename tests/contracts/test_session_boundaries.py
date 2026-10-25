"""Regression tests for the target session package boundaries."""

from __future__ import annotations

import ast
import importlib


TARGET_MODULES = (
    "tenon.session.runtime",
    "tenon.session.events",
    "tenon.session.persistence",
    "tenon.session.compaction",
    "tenon.session.navigation",
)


def test_target_session_packages_are_importable() -> None:
    for module_name in TARGET_MODULES:
        assert importlib.import_module(module_name) is not None


def test_session_subpackages_do_not_import_forbidden_layers() -> None:
    from pathlib import Path

    session_root = Path(__file__).resolve().parents[2] / "src" / "tenon" / "session"
    forbidden = ("tenon.ai", "tenon.tools", "tenon.config")
    for path in session_root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.append(node.module)
        violations = [
            module
            for module in imported
            if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)
        ]
        assert not violations, f"{path} imports forbidden layers: {violations}"
