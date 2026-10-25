"""扩展工具权限规则与 fail-closed 分类测试。"""

from __future__ import annotations

import json

from tenon.tools.plugins.permissions import parse_extension_permissions
from tenon.tools.security import ALLOW, ASK, DENY, classify_tool
from tenon.tools.security.permission_rules import ThreeTierPermissionRules


def test_missing_or_broken_config_returns_empty_rules(tmp_path):
    assert parse_extension_permissions(tmp_path) == ThreeTierPermissionRules.empty()
    (tmp_path / "extensions.json").write_text("{oops", encoding="utf-8")
    assert parse_extension_permissions(tmp_path) == ThreeTierPermissionRules.empty()


def test_three_tier_rules_parse_and_precedence(tmp_path):
    (tmp_path / "extensions.json").write_text(
        json.dumps(
            {
                "permissions": {
                    "deny": ["ext__evil__*"],
                    "ask": ["ext__demo__secret"],
                    "allow": ["ext__demo__*", "ext__evil__ok"],
                }
            }
        ),
        encoding="utf-8",
    )
    rules = parse_extension_permissions(tmp_path)
    assert rules.decide("ext__evil__tool") == "deny"  # deny 优先于 allow
    assert rules.decide("ext__evil__ok") == "deny"
    assert rules.decide("ext__demo__secret") == "ask"  # ask 优先于 allow
    assert rules.decide("ext__demo__hello") == "allow"
    assert rules.decide("ext__other__hello") is None


def test_ext_tools_fail_closed_without_rules(tmp_path):
    decision = classify_tool("ext__demo__hello", {}, workspace=tmp_path)
    assert decision.action == ASK
    assert decision.reason


def test_ext_tools_honor_allow_and_deny_rules(tmp_path):
    allow = ThreeTierPermissionRules(allow=("ext__demo__*",))
    deny = ThreeTierPermissionRules(deny=("ext__demo__hello",), allow=("ext__demo__*",))
    assert (
        classify_tool("ext__demo__hello", {}, workspace=tmp_path, ext_rules=allow).action == ALLOW
    )
    assert classify_tool("ext__demo__hello", {}, workspace=tmp_path, ext_rules=deny).action == DENY
