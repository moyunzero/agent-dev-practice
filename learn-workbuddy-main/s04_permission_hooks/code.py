#!/usr/bin/env python3
"""s04_permission_hooks.py - explicit permission governance for tool calls.

s03 decided which tool schemas enter a model session.  This lesson governs the
next boundary: whether a requested tool may actually cross into local execution.
It deliberately separates three stages that should not be hidden in one hook:

    PermissionPolicy.decide()     -> allow | ask | deny + rule + reason
    resolve_permission()          -> approval outcome (only for ask)
    GovernedToolRunner.run()      -> blocked | succeeded | failed result

Hooks observe those lifecycle stages for audit and post-processing.  They do not
silently turn a denied decision into an allowed one.  The command rules remain a
teaching preflight guard, not an operating-system sandbox.

Usage:
    python s04_permission_hooks/code.py
"""

from __future__ import annotations

import glob as globmod
import json
import os
import re
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# Machine-readable learning path metadata. Tests enforce that every chapter
# declares what it inherits and what it adds.
PROGRESSION = {
    "chapter": "s04_permission_hooks",
    "builds_on": ["s03_deferred_loading"],
    "adds": [
        "allow ask deny permission decisions",
        "workspace path scope",
        "separate user approval",
        "auditable execution outcomes",
    ],
    "preserves": ["multi-tool execution boundary", "hook lifecycle"],
}

# Shared learning entrypoints: --demo is offline; --provider deepseek configures
# a real API environment before this standalone lesson loads.
import sys as _wb_sys
from pathlib import Path as _wb_Path

_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
if str(_WB_ROOT) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_WB_ROOT))
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo

_wb_maybe_run_chapter_demo(__file__, PROGRESSION)
from mini_workbuddy.chapter_demo import prepare_chapter_provider as _wb_prepare_chapter_provider

_wb_prepare_chapter_provider()

try:
    import readline

    readline.parse_and_bind("set bind-tty-special-chars off")
    readline.parse_and_bind("set input-meta on")
    readline.parse_and_bind("set output-meta on")
    readline.parse_and_bind("set convert-meta off")
except ImportError:
    pass

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"):
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd().resolve()
MAX_TURNS = 8
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID")
if not MODEL:
    raise SystemExit(
        "MODEL_ID is not set. Copy .env.example to .env and fill in "
        "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
    )

SYSTEM = (
    f"You are a coding agent at {WORKDIR}. "
    "Tool calls are governed by workspace policy and may require approval."
)


# ═══════════════════════════════════════════════════════════════════
# Tool Implementations (the local side of the execution boundary)
# ═══════════════════════════════════════════════════════════════════

def safe_path(path_text: str) -> Path:
    """Resolve a path inside WORKDIR; execution repeats the policy boundary."""

    path = (WORKDIR / path_text).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {path_text}")
    return path


def run_bash(command: str) -> str:
    """Run the approved command; shell isolation is outside this lesson."""

    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = (completed.stdout + completed.stderr).strip()
        return output[:50_000] if output else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"
    except (FileNotFoundError, OSError) as exc:
        return f"Error: {exc}"


def run_read(path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(path).read_text(encoding="utf-8").splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def run_write(path: str, content: str) -> str:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} chars to {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_edit(path: str, old_text: str, new_text: str) -> str:
    try:
        file_path = safe_path(path)
        text = file_path.read_text(encoding="utf-8")
        if old_text not in text:
            return f"Error: text not found in {path}"
        file_path.write_text(text.replace(old_text, new_text, 1), encoding="utf-8")
        return f"Edited {path}"
    except Exception as exc:
        return f"Error: {exc}"


def run_glob(pattern: str) -> str:
    try:
        results = [
            str(Path(match).resolve().relative_to(WORKDIR))
            for match in globmod.glob(os.path.join(globmod.escape(str(WORKDIR)), pattern))
            if Path(match).resolve().is_relative_to(WORKDIR)
        ]
        return "\n".join(results) if results else "(no matches)"
    except Exception as exc:
        return f"Error: {exc}"


# ═══════════════════════════════════════════════════════════════════
# Provider-neutral Requests and Permission Decisions
# ═══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ToolRequest:
    """The provider-neutral subset of a tool_use block needed by governance."""

    tool_use_id: str
    name: str
    arguments: object

    @classmethod
    def from_block(cls, block: Any) -> ToolRequest:
        return cls(
            tool_use_id=str(getattr(block, "id", "")),
            name=str(getattr(block, "name", "")),
            arguments=getattr(block, "input", {}),
        )


class PermissionAction(str, Enum):
    """The complete output vocabulary of the pure policy stage."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionDecision:
    """A policy answer with enough evidence to explain and audit it."""

    request: ToolRequest
    action: PermissionAction
    rule_id: str
    reason: str


RuleMatcher = Callable[[ToolRequest], bool]
RuleExplainer = Callable[[ToolRequest], str]


@dataclass(frozen=True)
class PermissionRule:
    """One ordered policy rule; the first match wins."""

    rule_id: str
    action: PermissionAction
    matches: RuleMatcher
    explain: RuleExplainer

    def evaluate(self, request: ToolRequest) -> PermissionDecision | None:
        if not self.matches(request):
            return None
        return PermissionDecision(
            request=request,
            action=self.action,
            rule_id=self.rule_id,
            reason=self.explain(request),
        )


class WorkspaceScope:
    """Classify file-tool arguments against one resolved workspace root.

    ``resolve(strict=False)`` follows existing symlinks while still allowing a
    not-yet-created final path.  That catches a write through ``workspace/link``
    when the link points outside the workspace.  It is still a preflight check,
    so production code also needs OS isolation to close time-of-check/time-of-use
    races.
    """

    PATH_ARGUMENTS = {
        "read_file": "path",
        "write_file": "path",
        "edit_file": "path",
        "glob": "pattern",
    }

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve(strict=True)

    def argument_text(self, request: ToolRequest) -> str | None:
        if not isinstance(request.arguments, Mapping):
            return None
        key = self.PATH_ARGUMENTS.get(request.name)
        if key is None:
            return None
        raw = request.arguments.get(key)
        return raw if isinstance(raw, str) and raw else None

    def contains(self, request: ToolRequest) -> bool:
        raw = self.argument_text(request)
        if raw is None:
            return False
        candidate_text = self._static_glob_prefix(raw) if request.name == "glob" else raw
        candidate = Path(candidate_text).expanduser()
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            return candidate.resolve(strict=False).is_relative_to(self.root)
        except (OSError, RuntimeError):
            # Resolution failures and symlink loops fail closed.
            return False

    @staticmethod
    def _static_glob_prefix(pattern: str) -> str:
        """Return the non-wildcard prefix whose directory scope can be checked."""

        parts: list[str] = []
        for part in Path(pattern).parts:
            if globmod.has_magic(part):
                break
            parts.append(part)
        return str(Path(*parts)) if parts else "."


PATH_TOOLS = frozenset(WorkspaceScope.PATH_ARGUMENTS)
READ_PATH_TOOLS = frozenset({"read_file", "glob"})
WRITE_PATH_TOOLS = frozenset({"write_file", "edit_file"})

HARD_DENY_PATTERNS = (
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\brm\s+-(?=[^\s]*r)(?=[^\s]*f)[^\s]*", re.IGNORECASE),
    re.compile(r"\b(?:shutdown|reboot|mkfs(?:\.[a-z0-9]+)?)\b", re.IGNORECASE),
    re.compile(r"\bdd\s+[^\n]*(?:\bif=|\bof=/dev/)", re.IGNORECASE),
    re.compile(r">\s*/dev/(?:sd|disk)", re.IGNORECASE),
)

def _arguments(request: ToolRequest) -> Mapping[str, Any] | None:
    return request.arguments if isinstance(request.arguments, Mapping) else None


def _command(request: ToolRequest) -> str:
    arguments = _arguments(request)
    raw = arguments.get("command") if arguments else None
    return raw if isinstance(raw, str) else ""


def _bash_is_hard_denied(request: ToolRequest) -> bool:
    command = _command(request)
    return request.name == "bash" and any(pattern.search(command) for pattern in HARD_DENY_PATTERNS)


def _permission_input_error(request: ToolRequest, scope: WorkspaceScope) -> str | None:
    arguments = _arguments(request)
    if arguments is None:
        return "tool arguments must be an object"
    if request.name == "bash" and not _command(request).strip():
        return "bash requires a non-empty command"
    if request.name in PATH_TOOLS and scope.argument_text(request) is None:
        key = WorkspaceScope.PATH_ARGUMENTS[request.name]
        return f"{request.name} requires a non-empty string {key!r}"
    return None


class PermissionPolicy:
    """Evaluate ordered rules without prompting, executing, or mutating state."""

    def __init__(self, scope: WorkspaceScope) -> None:
        self.scope = scope
        self.rules = self._build_rules()

    def decide(self, request: ToolRequest) -> PermissionDecision:
        input_error = _permission_input_error(request, self.scope)
        if input_error:
            return PermissionDecision(
                request,
                PermissionAction.DENY,
                "request.invalid_arguments",
                input_error,
            )

        for rule in self.rules:
            decision = rule.evaluate(request)
            if decision is not None:
                return decision

        # An unmatched tool is not implicitly safe.  Adding a handler without an
        # explicit policy rule therefore fails closed and leaves an audit reason.
        return PermissionDecision(
            request,
            PermissionAction.DENY,
            "default.deny",
            f"no permission rule matched tool {request.name!r}",
        )

    def _build_rules(self) -> tuple[PermissionRule, ...]:
        scope = self.scope
        return (
            PermissionRule(
                "bash.hard_deny",
                PermissionAction.DENY,
                _bash_is_hard_denied,
                lambda request: f"command matches a non-overridable deny rule: {_command(request)!r}",
            ),
            PermissionRule(
                "path.outside_workspace",
                PermissionAction.DENY,
                lambda request: request.name in PATH_TOOLS and not scope.contains(request),
                lambda request: (
                    f"path {scope.argument_text(request)!r} resolves outside workspace "
                    f"{str(scope.root)!r}"
                ),
            ),
            PermissionRule(
                "path.read_allow",
                PermissionAction.ALLOW,
                lambda request: request.name in READ_PATH_TOOLS and scope.contains(request),
                lambda _request: "read-only file operation stays inside the workspace",
            ),
            PermissionRule(
                "path.write_requires_approval",
                PermissionAction.ASK,
                lambda request: request.name in WRITE_PATH_TOOLS and scope.contains(request),
                lambda request: (
                    f"{request.name} mutates workspace content and requires user approval"
                ),
            ),
            PermissionRule(
                "bash.requires_approval",
                PermissionAction.ASK,
                lambda request: request.name == "bash",
                lambda request: (
                    "shell strings cannot prove path scope or side effects; approval required: "
                    f"{_command(request)!r}"
                ),
            ),
        )


# ═══════════════════════════════════════════════════════════════════
# User Approval (separate from pure rule matching)
# ═══════════════════════════════════════════════════════════════════

class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class PermissionResolution:
    """A policy decision plus the independent user-approval outcome."""

    decision: PermissionDecision
    allowed: bool
    approval_status: ApprovalStatus


Approver = Callable[[PermissionDecision], bool]


def resolve_permission(
    decision: PermissionDecision,
    approver: Approver,
) -> PermissionResolution:
    """Resolve ASK through one injected UI boundary; ALLOW/DENY never prompt."""

    if decision.action is PermissionAction.ALLOW:
        return PermissionResolution(decision, True, ApprovalStatus.NOT_REQUIRED)
    if decision.action is PermissionAction.DENY:
        return PermissionResolution(decision, False, ApprovalStatus.NOT_REQUIRED)
    try:
        approved = bool(approver(decision))
    except KeyboardInterrupt:
        return PermissionResolution(decision, False, ApprovalStatus.CANCELLED)
    except Exception:
        # A closed or failed approval UI must fail closed rather than execute.
        return PermissionResolution(decision, False, ApprovalStatus.CANCELLED)
    return PermissionResolution(
        decision,
        approved,
        ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
    )


def console_approver(decision: PermissionDecision) -> bool:
    """The CLI's approval UI; replace this callback in desktop or test harnesses."""

    request = decision.request
    print(f"\n\033[33m⚠ Approval needed: {decision.reason}\033[0m")
    print(f"   Rule: {decision.rule_id}")
    print(f"   Tool: {request.name}")
    print(f"   Input: {json.dumps(request.arguments, ensure_ascii=False, default=str)[:300]}")
    return input("   Allow? [y/N] ").strip().lower() == "y"


# ═══════════════════════════════════════════════════════════════════
# Hooks and Audit Records
# ═══════════════════════════════════════════════════════════════════

Hook = Callable[..., None]


class HookRegistry:
    """Lifecycle extension points kept outside the authorization decision."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Hook]] = {
            "PreToolUse": [],
            "PermissionDecision": [],
            "PostToolUse": [],
            "UserPromptSubmit": [],
            "Stop": [],
        }

    def register(self, event: str, hook: Hook) -> None:
        self._hooks.setdefault(event, []).append(hook)

    def emit(self, event: str, *args: object) -> None:
        for hook in self._hooks.get(event, []):
            hook(*args)

    def handlers(self, event: str) -> tuple[Hook, ...]:
        return tuple(self._hooks.get(event, ()))


@dataclass(frozen=True)
class AuditRecord:
    """One in-memory teaching record; s23 adds tamper-evident persistence."""

    event: str
    tool_name: str
    rule_id: str = ""
    reason: str = ""
    outcome: str = ""


class AuditTrail:
    """Collect request, decision, and result facts without hiding the reason."""

    def __init__(self) -> None:
        self.records: list[AuditRecord] = []

    def record_request(self, request: ToolRequest) -> None:
        self.records.append(AuditRecord("request", request.name))

    def record_permission(self, resolution: PermissionResolution) -> None:
        decision = resolution.decision
        if decision.action is PermissionAction.ALLOW:
            outcome = "allowed"
        elif decision.action is PermissionAction.DENY:
            outcome = "denied"
        else:
            outcome = resolution.approval_status.value
        self.records.append(
            AuditRecord(
                event="permission",
                tool_name=decision.request.name,
                rule_id=decision.rule_id,
                reason=decision.reason,
                outcome=outcome,
            )
        )

    def record_result(self, result: ToolExecutionResult) -> None:
        self.records.append(
            AuditRecord(
                event="result",
                tool_name=result.request.name,
                rule_id=result.permission.decision.rule_id,
                reason=result.permission.decision.reason,
                outcome=result.status.value,
            )
        )


def output_size_hook(result: ToolExecutionResult) -> None:
    if len(result.content) > 10_000:
        print(
            f"\033[33m[warn] Large output: {len(result.content)} chars "
            f"from {result.request.name}\033[0m"
        )


def build_hooks(audit: AuditTrail) -> HookRegistry:
    """Assemble the built-in observable lifecycle in one explicit place."""

    hooks = HookRegistry()
    hooks.register("PreToolUse", audit.record_request)
    hooks.register("PermissionDecision", audit.record_permission)
    hooks.register("PostToolUse", audit.record_result)
    hooks.register("PostToolUse", output_size_hook)
    hooks.register(
        "Stop",
        lambda: print(f"\033[90m[stats] {len(audit.records)} governance records\033[0m"),
    )
    return hooks


# ═══════════════════════════════════════════════════════════════════
# Governed Execution Result
# ═══════════════════════════════════════════════════════════════════

class ToolExecutionStatus(str, Enum):
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolExecutionResult:
    """The result of policy, approval, and optional handler execution."""

    request: ToolRequest
    permission: PermissionResolution
    status: ToolExecutionStatus
    content: str

    def to_protocol_block(self) -> dict[str, Any]:
        block: dict[str, Any] = {
            "type": "tool_result",
            "tool_use_id": self.request.tool_use_id,
            "content": self.content,
        }
        if self.status is not ToolExecutionStatus.SUCCEEDED:
            block["is_error"] = True
        return block


ToolHandler = Callable[..., str]


class GovernedToolRunner:
    """Run the three governance stages and emit hooks at visible boundaries."""

    def __init__(
        self,
        policy: PermissionPolicy,
        handlers: Mapping[str, ToolHandler],
        approver: Approver,
        hooks: HookRegistry,
    ) -> None:
        self.policy = policy
        self.handlers = dict(handlers)
        self.approver = approver
        self.hooks = hooks

    def run(self, request: ToolRequest) -> ToolExecutionResult:
        self.hooks.emit("PreToolUse", request)

        decision = self.policy.decide(request)
        permission = resolve_permission(decision, self.approver)
        self.hooks.emit("PermissionDecision", permission)

        if not permission.allowed:
            result = ToolExecutionResult(
                request=request,
                permission=permission,
                status=ToolExecutionStatus.BLOCKED,
                content=(
                    f"Permission blocked [{decision.rule_id}]: {decision.reason} "
                    f"(approval={permission.approval_status.value})"
                ),
            )
            self.hooks.emit("PostToolUse", result)
            return result

        handler = self.handlers.get(request.name)
        if handler is None:
            result = ToolExecutionResult(
                request,
                permission,
                ToolExecutionStatus.FAILED,
                f"Execution failed: no handler registered for {request.name!r}",
            )
            self.hooks.emit("PostToolUse", result)
            return result

        try:
            # PermissionPolicy rejects non-object arguments before this expansion.
            arguments = dict(request.arguments)  # type: ignore[arg-type]
            content = str(handler(**arguments))
            status = ToolExecutionStatus.SUCCEEDED
        except Exception as exc:
            content = f"Execution failed for {request.name}: {exc}"
            status = ToolExecutionStatus.FAILED

        result = ToolExecutionResult(request, permission, status, content)
        self.hooks.emit("PostToolUse", result)
        return result


# A small compatibility helper keeps the chapter easy to try in a REPL while
# routing every decision through the new structured policy.
def check_permission(tool_name: str, tool_input: object) -> tuple[str, str]:
    decision = PERMISSION_POLICY.decide(ToolRequest("manual", tool_name, tool_input))
    return decision.action.value, decision.reason


# ═══════════════════════════════════════════════════════════════════
# Tool Definitions and Agent Loop
# ═══════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "bash",
        "description": "Run a shell command after permission review and user approval.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a workspace file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "limit": {"type": "integer"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write a workspace file after approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": "Replace exact text in a workspace file after approval.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "glob",
        "description": "Find files matching a workspace-relative glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "bash": run_bash,
    "read_file": run_read,
    "write_file": run_write,
    "edit_file": run_edit,
    "glob": run_glob,
}

PERMISSION_POLICY = PermissionPolicy(WorkspaceScope(WORKDIR))
AUDIT_TRAIL = AuditTrail()
HOOKS = build_hooks(AUDIT_TRAIL)
RUNNER = GovernedToolRunner(
    policy=PERMISSION_POLICY,
    handlers=TOOL_HANDLERS,
    approver=console_approver,
    hooks=HOOKS,
)


def agent_loop(messages: list[dict[str, Any]], max_turns: int = MAX_TURNS) -> None:
    """Run a bounded loop whose every tool result crosses governance first."""

    for _turn in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            system=SYSTEM,
            messages=messages,
            tools=TOOLS,
            max_tokens=8_000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            HOOKS.emit("Stop")
            return

        protocol_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            result = RUNNER.run(ToolRequest.from_block(block))
            color = "36" if result.status is ToolExecutionStatus.SUCCEEDED else "31"
            print(f"\033[{color}m> {result.request.name}\033[0m {result.content[:120]}")
            protocol_results.append(result.to_protocol_block())

        messages.append({"role": "user", "content": protocol_results})

    # Reaching the budget is a harness stop condition, not permission success.
    HOOKS.emit("Stop")
    print(f"\033[31mStopped after max_turns={max_turns}\033[0m")


if __name__ == "__main__":
    print("s04: Permission & Hooks — decide, approve, then execute")
    print("输入问题，回车发送。输入 q 退出。\n")
    history: list[dict[str, Any]] = []
    while True:
        try:
            query = input("\033[36ms04 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in {"q", "exit", ""}:
            break
        HOOKS.emit("UserPromptSubmit", query)
        history.append({"role": "user", "content": query})
        agent_loop(history)
        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
