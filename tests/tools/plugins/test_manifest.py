"""插件 manifest 解析契约测试。"""

from __future__ import annotations

import json

import pytest

from codeagent.tools.plugins.manifest import parse_plugin_manifest
from tests.tools.plugins.fixtures import make_plugin

pytestmark = pytest.mark.contract


def test_parses_valid_manifest(tmp_path):
    plugin_dir = make_plugin(tmp_path, "demo")
    manifest, diags = parse_plugin_manifest(plugin_dir)
    assert diags == []
    assert manifest is not None
    assert manifest.plugin_id == "demo"
    assert manifest.module == "plugin.py"
    assert manifest.tools == ("hello",)


def test_invalid_id_rejected(tmp_path):
    for bad_id in ("Demo", "de__mo", "1demo"):
        plugin_dir = make_plugin(tmp_path, f"p{len(bad_id)}x", manifest={"id": bad_id})
        manifest, diags = parse_plugin_manifest(plugin_dir)
        assert manifest is None
        assert any("非法插件 id" in diag for diag in diags)


def test_missing_module_field_rejected(tmp_path):
    plugin_dir = make_plugin(tmp_path, "demo")
    raw = json.loads((plugin_dir / "codeagent-plugin.json").read_text(encoding="utf-8"))
    raw.pop("module")
    (plugin_dir / "codeagent-plugin.json").write_text(json.dumps(raw), encoding="utf-8")
    manifest, diags = parse_plugin_manifest(plugin_dir)
    assert manifest is None
    assert any("缺少 module" in diag for diag in diags)


def test_module_escape_rejected(tmp_path):
    plugin_dir = make_plugin(tmp_path, "demo", manifest={"module": "../outside.py"})
    manifest, diags = parse_plugin_manifest(plugin_dir)
    assert manifest is None
    assert any("越出插件目录" in diag for diag in diags)


def test_invalid_tool_declaration_warns_but_parses(tmp_path):
    plugin_dir = make_plugin(tmp_path, "demo", manifest={"tools": ["hello", "Bad Name"]})
    manifest, diags = parse_plugin_manifest(plugin_dir)
    assert manifest is not None
    assert manifest.tools == ("hello",)
    assert any("非法工具名声明" in diag for diag in diags)


def test_broken_json_reports_diagnostic(tmp_path):
    plugin_dir = tmp_path / "demo"
    plugin_dir.mkdir()
    (plugin_dir / "codeagent-plugin.json").write_text("{oops", encoding="utf-8")
    manifest, diags = parse_plugin_manifest(plugin_dir)
    assert manifest is None
    assert any("manifest 读取失败" in diag for diag in diags)
