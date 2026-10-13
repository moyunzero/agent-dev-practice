"""Offline contracts for declarative Skill and MCP permissions."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_chapter(module_name: str, chapter: str):
    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    os.environ["MODEL_ID"] = "offline-test-model"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name, ROOT / chapter / "code.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(stub_dir))
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
        if old_model is None:
            os.environ.pop("MODEL_ID", None)
        else:
            os.environ["MODEL_ID"] = old_model


@pytest.fixture(scope="module")
def s16():
    module_name = "s16_skill_permissions_test_module"
    module = _load_chapter(module_name, "s16_skills_system")
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)


@pytest.fixture(scope="module")
def s17():
    module_name = "s17_skill_permissions_test_module"
    module = _load_chapter(module_name, "s17_mcp_connectors")
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)


def _skill_markdown(permissions: str) -> str:
    return f"""---
title: docs-reader
summary: Read project documentation
read_when: [docs]
agent_created: true
permissions:
{permissions}
---

# Docs reader
Read the requested documentation before answering.
"""


def test_s16_parses_strict_permission_manifest(s16, tmp_path: Path) -> None:
    skill_path = tmp_path / "SKILL.md"
    skill_path.write_text(
        _skill_markdown(
            "  tools: [read_file]\n"
            "  network: false\n"
            "  paths:\n"
            "    read: [\"./docs/**\"]\n"
            "    write: []"
        ),
        encoding="utf-8",
    )

    skill = s16.parse_skill_md(skill_path)

    assert skill is not None
    assert skill.permissions.tools == ("read_file",)
    assert skill.permissions.network is False
    assert skill.permissions.read_paths == ("docs/**",)
    assert skill.permissions.write_paths == ()


@pytest.mark.parametrize(
    "permissions, message",
    [
        ("  tools: [read_file]\n  shell: true", "unknown permissions fields"),
        ("  tools: read_file", "permissions.tools must be a list"),
        (
            "  paths:\n    read: [\"../private/**\"]",
            "must not escape the workspace",
        ),
        (
            "  paths:\n    write: [\"C:/Users/private/**\"]",
            "must stay relative to the workspace",
        ),
    ],
)
def test_s16_rejects_unknown_or_escaping_permissions(
    s16, permissions: str, message: str
) -> None:
    frontmatter, _ = s16.parse_frontmatter(_skill_markdown(permissions))

    with pytest.raises(s16.SkillPermissionError, match=message):
        s16.parse_skill_permissions(frontmatter["permissions"])


def test_s16_runtime_gate_checks_tool_network_and_path(s16, tmp_path: Path) -> None:
    skill = s16.Skill(
        title="docs-reader",
        summary="Read docs",
        read_when=["docs"],
        path="(test)",
        permissions=s16.SkillPermissions(
            tools=("read_file", "bash"),
            network=False,
            read_paths=("docs/**",),
        ),
    )

    allowed, _ = s16.authorize_skill_tool(
        skill, "read_file", {"path": "docs/guide.md"}, workdir=tmp_path
    )
    escaped, escaped_reason = s16.authorize_skill_tool(
        skill, "read_file", {"path": "../secret.txt"}, workdir=tmp_path
    )
    undeclared, undeclared_reason = s16.authorize_skill_tool(
        skill, "write_file", {"path": "docs/output.md"}, workdir=tmp_path
    )
    networked, network_reason = s16.authorize_skill_tool(
        skill, "bash", {"command": "git clone https://example.invalid/repo"}
    )

    assert allowed is True
    assert escaped is False and "cannot read path" in escaped_reason
    assert undeclared is False and "did not declare tool" in undeclared_reason
    assert networked is False and "network access" in network_reason


def test_s16_loaded_skill_overlay_restricts_base_tools(s16, tmp_path: Path) -> None:
    original = list(s16.loaded_skills)
    s16.loaded_skills[:] = [
        s16.Skill(
            title="docs-reader",
            summary="Read docs",
            read_when=["docs"],
            path="(test)",
            permissions=s16.SkillPermissions(
                tools=("read_file",), read_paths=("docs/**",)
            ),
        )
    ]
    try:
        read_allowed, _ = s16.authorize_loaded_skill_tool(
            "read_file", {"path": "docs/guide.md"}, workdir=tmp_path
        )
        bash_allowed, reason = s16.authorize_loaded_skill_tool(
            "bash", {"command": "git status"}, workdir=tmp_path
        )
    finally:
        s16.loaded_skills[:] = original

    assert read_allowed is True
    assert bash_allowed is False
    assert "did not declare tool" in reason


def test_s16_audit_surfaces_permission_escalation(s16) -> None:
    previous = s16.SkillPermissions(
        tools=("read_file",), read_paths=("docs/**",)
    )
    updated = _skill_markdown(
        "  tools: [read_file, bash]\n"
        "  network: false\n"
        "  paths:\n"
        "    read: [\"docs/**\"]\n"
        "    write: []"
    )

    level, report = s16.audit_skill(updated, previous)

    assert level == "P1"
    assert "扩大权限" in report
    assert "bash" in report


def test_s16_safe_read_only_manifest_remains_p2(s16) -> None:
    level, report = s16.audit_skill(
        _skill_markdown(
            "  tools: [read_file]\n"
            "  network: false\n"
            "  paths:\n"
            "    read: [\"docs/**\"]\n"
            "    write: []"
        )
    )

    assert level == "P2"
    assert "安全" in report


def test_s17_trust_without_skill_grant_exposes_no_tools(s17) -> None:
    manager = s17.ConnectorManager(s17.MCP_CONFIG)
    assert manager.trust_connector("github") is True

    assert manager.get_deferred_tools_list() == []
    denial = manager.tool_search("mcp__github__list_issues")
    assert denial["code"] == "permission_denied"
    assert "permission_denied" in manager.defer_execute_tool(
        "mcp__github__list_issues", {"repo": "owner/repo"}
    )


def test_s17_grant_filters_discovery_and_rechecks_execution(s17) -> None:
    allowed_tool = "mcp__github__list_issues"
    manager = s17.ConnectorManager(
        s17.MCP_CONFIG,
        s17.MCPPermissionGrant(tools={allowed_tool}, network=True),
    )
    manager.trust_all()

    assert [tool["name"] for tool in manager.get_deferred_tools_list()] == [
        allowed_tool
    ]
    schema = manager.tool_search(allowed_tool)
    assert schema["name"] == allowed_tool

    result = json.loads(
        manager.defer_execute_tool(allowed_tool, {"repo": "owner/repo"})
    )
    assert result["status"] == "ok"

    manager.set_permission_grant(s17.NO_MCP_PERMISSIONS)
    revoked = json.loads(
        manager.defer_execute_tool(allowed_tool, {"repo": "owner/repo"})
    )
    assert revoked["code"] == "permission_denied"


def test_s17_tool_allowlist_still_requires_network_permission(s17) -> None:
    tool_name = "mcp__github__list_issues"
    manager = s17.ConnectorManager(
        s17.MCP_CONFIG,
        s17.MCPPermissionGrant(tools={tool_name}, network=False),
    )
    manager.trust_connector("github")

    assert manager.get_deferred_tools_list() == []
    assert manager.tool_search(tool_name)["code"] == "permission_denied"


def test_s17_rejects_non_namespaced_or_malformed_grants(s17) -> None:
    with pytest.raises(ValueError, match="collection"):
        s17.MCPPermissionGrant(tools="mcp__github__list_issues", network=True)
    with pytest.raises(ValueError, match="namespaced"):
        s17.MCPPermissionGrant(tools={"list_issues"}, network=True)
    with pytest.raises(ValueError, match="true or false"):
        s17.MCPPermissionGrant(tools=set(), network="yes")
