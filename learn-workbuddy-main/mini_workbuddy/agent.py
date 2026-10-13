from __future__ import annotations

import re
from dataclasses import asdict

from .audit import AuditLog
from .events import EventBus
from .storage import SessionRecord, Storage
from .tools import PermissionError, ToolRegistry


class MiniAgent:
    """A deterministic teaching agent.

    Real WorkBuddy delegates reasoning to an LLM. This mini version keeps the
    harness visible by using simple intent parsing while preserving the same
    message -> tool -> result -> event shape.
    """

    def __init__(
        self,
        storage: Storage,
        tools: ToolRegistry,
        events: EventBus,
        audit: AuditLog | None = None,
    ) -> None:
        self.storage = storage
        self.tools = tools
        self.events = events
        self.audit = audit

    def prompt(self, session: SessionRecord, text: str) -> dict:
        user_event = self.storage.append_event(
            session,
            {"type": "message", "role": "user", "content": text},
        )
        self._audit(
            "user_prompt",
            {"sessionId": session.id, "text": text},
            user_event,
        )
        self._publish(
            session,
            user_event,
            {"role": "user", "content": text},
        )

        plan = self._plan(text)
        if plan is None:
            answer = (
                "Mini WorkBuddy is alive. Try: `list files`, `pwd`, "
                "`read README.md`, or `tools`."
            )
            self._assistant(session, answer)
            return {"answer": answer, "toolResults": []}

        tool_name, argument = plan
        # Allocate the correlation ID before execution so a crash, denial, or
        # timeout still leaves a durable record of what the harness attempted.
        tool_call_id = self.tools.new_call_id(tool_name)
        tool_call_event = self.storage.append_event(
            session,
            {
                "type": "tool_call",
                "tool_call_id": tool_call_id,
                "tool": tool_name,
                "argument": argument,
            },
        )
        self._publish(
            session,
            tool_call_event,
            {
                "type": "tool_call",
                "tool_call_id": tool_call_id,
                "tool": tool_name,
                "argument": argument,
            },
        )
        self._audit(
            "tool_call",
            {
                "sessionId": session.id,
                "toolCallId": tool_call_id,
                "tool": tool_name,
                "argument": argument,
            },
            tool_call_event,
        )
        try:
            result = self.tools.run(
                tool_name,
                argument,
                session,
                tool_call_id=tool_call_id,
            )
        except (PermissionError, OSError, KeyError, TimeoutError) as exc:
            answer = f"Tool failed: {exc}"
            result = None
            error_event = self.storage.append_event(
                session,
                {
                    "type": "tool_error",
                    "tool_call_id": tool_call_id,
                    "tool": tool_name,
                    "error": str(exc),
                },
            )
            self._publish(
                session,
                error_event,
                {
                    "type": "tool_error",
                    "tool_call_id": tool_call_id,
                    "tool": tool_name,
                    "error": str(exc),
                },
            )
            self._audit(
                "tool_error",
                {
                    "sessionId": session.id,
                    "toolCallId": tool_call_id,
                    "tool": tool_name,
                    "error": str(exc),
                },
                error_event,
            )
        else:
            # Only exceptions from tools.run belong to the tool-error branch.
            # A later persistence, publication, or audit failure does not undo
            # execution. Let it propagate without inventing a tool_error or
            # retrying a tool whose side effects may already have happened.
            result_data = asdict(result)
            result_event = self.storage.append_event(
                session,
                {"type": "tool_result", **result_data},
            )
            self._publish(
                session,
                result_event,
                {"type": "tool_result", **result_data},
            )
            self._audit(
                "tool_result",
                {
                    "sessionId": session.id,
                    "toolCallId": tool_call_id,
                    "tool": result.name,
                    "externalized": result.externalized_path is not None,
                    "exit_code": result.exit_code,
                },
                result_event,
            )
            answer = self._summarize_result(result.content)

        self._assistant(session, answer)
        return {"answer": answer, "toolResults": [asdict(result)] if result else []}

    def _assistant(self, session: SessionRecord, content: str) -> None:
        assistant_event = self.storage.append_event(
            session,
            {"type": "message", "role": "assistant", "content": content},
        )
        self._audit(
            "assistant_message",
            {"sessionId": session.id, "content": content[:500]},
            assistant_event,
        )
        self._publish(
            session,
            assistant_event,
            {"role": "assistant", "content": content},
        )

    def _audit(
        self,
        action: str,
        data: dict,
        transcript_event: dict,
    ) -> None:
        if self.audit is not None:
            self.audit.append(
                action,
                {
                    **data,
                    "transcriptEventId": transcript_event["event_id"],
                },
            )

    def _publish(
        self,
        session: SessionRecord,
        transcript_event: dict,
        data: dict,
    ) -> None:
        """Publish only after the corresponding transcript event is durable."""

        self.events.publish(
            "session_update",
            {
                "sessionId": session.id,
                "eventId": transcript_event["event_id"],
                "sequence": transcript_event["sequence"],
                **data,
            },
        )

    def _plan(self, text: str) -> tuple[str, str] | None:
        lowered = text.lower().strip()
        if lowered in {"tools", "tool search", "list tools"}:
            return ("tool_search", "")
        if lowered in {"pwd", "where am i"}:
            return ("bash", "pwd")
        if "list files" in lowered or lowered in {"ls", "dir"}:
            return ("bash", "ls -la")
        match = re.search(r"read\s+(.+)", text, re.IGNORECASE)
        if match:
            return ("read_file", match.group(1).strip())
        if lowered.startswith("bash "):
            return ("bash", text[5:].strip())
        return None

    def _summarize_result(self, content: str) -> str:
        if len(content) > 4_000:
            return content[:4_000] + "\n\n...[truncated in assistant summary]..."
        return content
