"""Contracts for the release artifact inspection helpers."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.release_check import PackageInspectionError, inspect_distribution


def _write_wheel(path: Path, *, version: str = "0.3.0", include_resources: bool = True) -> None:
    files = {
        f"tenon-{version}.dist-info/METADATA": (
            "Metadata-Version: 2.3\nName: tenon\nVersion: " + version + "\n"
        ),
        f"tenon-{version}.dist-info/RECORD": "",
        "tenon/__init__.py": "__version__ = '0.3.0'\n",
    }
    if include_resources:
        files.update(
            {
                "tenon/resources/prompts/system.md": "system",
                "tenon/resources/skills/commit-message/SKILL.md": "skill",
                "tenon/resources/skills/dependency-audit/SKILL.md": "skill",
            }
        )
    with ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def test_inspect_distribution_reports_required_resources_and_version(tmp_path: Path) -> None:
    wheel = tmp_path / "tenon-0.3.0-py3-none-any.whl"
    _write_wheel(wheel)

    report = inspect_distribution(wheel, expected_name="tenon", expected_version="0.3.0")

    assert report["status"] == "passed"
    assert report["version"] == "0.3.0"
    assert report["required_resources"] == 3


def test_inspect_distribution_rejects_missing_resources(tmp_path: Path) -> None:
    wheel = tmp_path / "tenon-0.3.0-py3-none-any.whl"
    _write_wheel(wheel, include_resources=False)

    with pytest.raises(PackageInspectionError, match="required resources"):
        inspect_distribution(wheel, expected_name="tenon", expected_version="0.3.0")


def test_inspect_distribution_rejects_sensitive_files(tmp_path: Path) -> None:
    wheel = tmp_path / "tenon-0.3.0-py3-none-any.whl"
    _write_wheel(wheel)
    with ZipFile(wheel, "a") as archive:
        archive.writestr(".env", "DEEPSEEK_API_KEY=secret")

    with pytest.raises(PackageInspectionError, match="sensitive"):
        inspect_distribution(wheel, expected_name="tenon", expected_version="0.3.0")
