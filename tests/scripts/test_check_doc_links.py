"""docs/check_doc_links 脚本行为测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.check_doc_links as check


def test_external_and_anchor_links_are_skipped(tmp_path, monkeypatch):
    doc = tmp_path / "doc.md"
    doc.write_text(
        "[a](https://example.com) [b](#section) [c](mailto:x@y.z)\n",
        encoding="utf-8",
    )
    assert check.broken_links(doc) == []


def test_existing_relative_link_passes(tmp_path):
    (tmp_path / "target.md").write_text("ok", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("[t](./target.md#part)\n", encoding="utf-8")
    assert check.broken_links(doc) == []


def test_missing_relative_link_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(check, "ROOT", tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text("[gone](./missing.md)\n", encoding="utf-8")
    broken = check.broken_links(doc)
    assert len(broken) == 1
    assert "missing.md" in broken[0]


def test_main_returns_nonzero_on_broken_link(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check, "ROOT", tmp_path)
    doc = tmp_path / "doc.md"
    doc.write_text("[gone](./missing.md)\n", encoding="utf-8")
    monkeypatch.setattr(check, "documents", lambda: [doc])

    assert check.main() == 1
    assert "失效链接" in capsys.readouterr().err


def test_main_passes_for_valid_documents(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(check, "ROOT", tmp_path)
    (tmp_path / "target.md").write_text("ok", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text("[ok](./target.md)\n", encoding="utf-8")
    monkeypatch.setattr(check, "documents", lambda: [doc])

    assert check.main() == 0
    assert "通过" in capsys.readouterr().out


@pytest.mark.parametrize("prefix", ["http://", "https://", "mailto:", "#"])
def test_is_external_prefixes(prefix):
    assert check.is_external(f"{prefix}rest")
