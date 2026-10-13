"""Behavior tests for s04's permission governance pipeline.

The lesson separates three questions that are easy to blur together:

1. What does policy decide (allow / ask / deny)?
2. If policy asks, what did the user approve?
3. Did the governed tool actually run, fail, or stay blocked?

The tests also document the chapter boundary: command rules are a useful
preflight guard, but operating-system isolation is still required in production.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s04():
    """Import the standalone chapter with the offline Anthropic stub."""

    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    os.environ["MODEL_ID"] = "offline-test-model"
    module_name = "s04_permission_hooks_test_module"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            ROOT / "s04_permission_hooks" / "code.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(stub_dir))
        sys.modules.pop(module_name, None)
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
        if old_model is None:
            os.environ.pop("MODEL_ID", None)
        else:
            os.environ["MODEL_ID"] = old_model


def request(s04, name: str, arguments: object, call_id: str = "call_1"):
    return s04.ToolRequest(call_id, name, arguments)


@pytest.mark.parametrize(
    "command",
    [
        "sudo apt install x",
        "rm -rf / --no-preserve-root",
        "rm -fr ./build",
        "mkfs.ext4 /dev/sda1",
        "dd if=/dev/zero of=/dev/sda",
    ],
)
def test_hard_denies_are_structured_decisions(s04, tmp_path: Path, command: str) -> None:
    policy = s04.PermissionPolicy(s04.WorkspaceScope(tmp_path))

    decision = policy.decide(request(s04, "bash", {"command": command}))

    assert decision.action is s04.PermissionAction.DENY
    assert decision.rule_id == "bash.hard_deny"
    assert decision.reason


def test_unmatched_tools_fail_closed_with_an_audit_reason(s04, tmp_path: Path) -> None:
    policy = s04.PermissionPolicy(s04.WorkspaceScope(tmp_path))

    decision = policy.decide(request(s04, "send_email", {"to": "a@example.com"}))

    assert decision.action is s04.PermissionAction.DENY
    assert decision.rule_id == "default.deny"
    assert "no permission rule matched" in decision.reason


def test_path_scope_allows_inside_and_denies_escape(s04, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "notes.md").write_text("hello", encoding="utf-8")
    (workspace / "link").symlink_to(outside, target_is_directory=True)
    policy = s04.PermissionPolicy(s04.WorkspaceScope(workspace))

    inside = policy.decide(request(s04, "read_file", {"path": "notes.md"}))
    traversal = policy.decide(request(s04, "read_file", {"path": "../outside/secret"}))
    absolute = policy.decide(request(s04, "write_file", {"path": "/etc/hosts", "content": "x"}))
    symlink = policy.decide(request(s04, "write_file", {"path": "link/new.txt", "content": "x"}))

    assert inside.action is s04.PermissionAction.ALLOW
    for decision in [traversal, absolute, symlink]:
        assert decision.action is s04.PermissionAction.DENY
        assert decision.rule_id == "path.outside_workspace"
        assert "workspace" in decision.reason


def test_policy_only_decides_and_never_prompts(s04, tmp_path: Path, monkeypatch) -> None:
    policy = s04.PermissionPolicy(s04.WorkspaceScope(tmp_path))
    monkeypatch.setattr("builtins.input", lambda _prompt: pytest.fail("policy prompted"))

    decision = policy.decide(
        request(s04, "write_file", {"path": "notes.md", "content": "hello"})
    )

    assert decision.action is s04.PermissionAction.ASK
    assert decision.rule_id == "path.write_requires_approval"


@pytest.mark.parametrize(
    ("command", "expected", "rule_id"),
    [
        ("ls -la", "ASK", "bash.requires_approval"),
        ("git diff --stat", "ASK", "bash.requires_approval"),
        ("cat /etc/passwd", "ASK", "bash.requires_approval"),
        ("python3 script.py", "ASK", "bash.requires_approval"),
        ("rm old.log", "ASK", "bash.requires_approval"),
        ("ls > files.txt", "ASK", "bash.requires_approval"),
    ],
)
def test_shell_policy_never_claims_path_safety_from_the_first_token(
    s04,
    tmp_path: Path,
    command: str,
    expected: str,
    rule_id: str,
) -> None:
    policy = s04.PermissionPolicy(s04.WorkspaceScope(tmp_path))

    decision = policy.decide(request(s04, "bash", {"command": command}))

    assert decision.action.name == expected
    assert decision.rule_id == rule_id


def test_approval_resolution_is_separate_and_deny_cannot_be_overridden(
    s04,
    tmp_path: Path,
) -> None:
    policy = s04.PermissionPolicy(s04.WorkspaceScope(tmp_path))
    asked: list[str] = []
    ask_decision = policy.decide(
        request(s04, "write_file", {"path": "notes.md", "content": "hello"})
    )

    approved = s04.resolve_permission(
        ask_decision,
        lambda decision: asked.append(decision.rule_id) or True,
    )
    rejected = s04.resolve_permission(ask_decision, lambda _decision: False)
    cancelled = s04.resolve_permission(
        ask_decision,
        lambda _decision: (_ for _ in ()).throw(RuntimeError("approval UI closed")),
    )
    denied = s04.resolve_permission(
        policy.decide(request(s04, "unknown", {})),
        lambda _decision: pytest.fail("deny must not ask for approval"),
    )

    assert approved.allowed is True
    assert approved.approval_status is s04.ApprovalStatus.APPROVED
    assert rejected.allowed is False
    assert rejected.approval_status is s04.ApprovalStatus.REJECTED
    assert cancelled.allowed is False
    assert cancelled.approval_status is s04.ApprovalStatus.CANCELLED
    assert denied.allowed is False
    assert denied.approval_status is s04.ApprovalStatus.NOT_REQUIRED
    assert asked == ["path.write_requires_approval"]


def test_governed_runner_records_decision_reason_and_execution_result(
    s04,
    tmp_path: Path,
) -> None:
    audit = s04.AuditTrail()
    hooks = s04.build_hooks(audit)
    writes: list[tuple[str, str]] = []
    runner = s04.GovernedToolRunner(
        policy=s04.PermissionPolicy(s04.WorkspaceScope(tmp_path)),
        handlers={
            "write_file": lambda path, content: writes.append((path, content)) or "written",
        },
        approver=lambda _decision: True,
        hooks=hooks,
    )

    result = runner.run(
        request(s04, "write_file", {"path": "notes.md", "content": "hello"})
    )

    assert result.status is s04.ToolExecutionStatus.SUCCEEDED
    assert result.content == "written"
    assert writes == [("notes.md", "hello")]
    decision_record = next(record for record in audit.records if record.event == "permission")
    result_record = next(record for record in audit.records if record.event == "result")
    assert decision_record.rule_id == "path.write_requires_approval"
    assert decision_record.reason == result.permission.decision.reason
    assert decision_record.outcome == "approved"
    assert result_record.outcome == "succeeded"


def test_blocked_and_failed_execution_are_results_not_control_flow(s04, tmp_path: Path) -> None:
    audit = s04.AuditTrail()
    runner = s04.GovernedToolRunner(
        policy=s04.PermissionPolicy(s04.WorkspaceScope(tmp_path)),
        handlers={
            "write_file": lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("disk full")),
        },
        approver=lambda _decision: True,
        hooks=s04.build_hooks(audit),
    )

    blocked = runner.run(request(s04, "unknown", {}))
    failed = runner.run(
        request(s04, "write_file", {"path": "notes.md", "content": "hello"})
    )

    assert blocked.status is s04.ToolExecutionStatus.BLOCKED
    assert blocked.to_protocol_block()["is_error"] is True
    assert "default.deny" in blocked.content
    assert failed.status is s04.ToolExecutionStatus.FAILED
    assert failed.to_protocol_block()["is_error"] is True
    assert "disk full" in failed.content


def test_s04_run_bash_reports_os_errors(s04, monkeypatch) -> None:
    def fake_run(*_args, **_kwargs):
        raise OSError("spawn failed")

    monkeypatch.setattr(s04.subprocess, "run", fake_run)
    assert s04.run_bash("echo hi") == "Error: spawn failed"
