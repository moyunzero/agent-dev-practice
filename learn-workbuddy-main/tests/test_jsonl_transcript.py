"""S09 transcript evidence and replay-state contracts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s09():
    name = "s09_jsonl_transcript_test_module"
    spec = importlib.util.spec_from_file_location(name, ROOT / "s09_jsonl_transcript" / "code.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


def test_append_wraps_copied_event_with_monotonic_evidence_envelope(s09, tmp_path: Path) -> None:
    transcript = s09.JSONLTranscript(tmp_path / "session.jsonl")
    source = {"type": "message", "role": "user", "content": "hello"}
    transcript.append(source)
    transcript.append({"type": "message", "role": "assistant", "content": "hi"})

    records = [json.loads(line) for line in transcript.path.read_text().splitlines()]
    assert [record["sequence"] for record in records] == [1, 2]
    assert all(record["schema_version"] == 1 for record in records)
    assert all(record["recorded_at"].endswith("+00:00") for record in records)
    assert [record["session_id"] for record in records] == ["session", "session"]
    assert [record["event_id"] for record in records] == [
        "transcript:session:1",
        "transcript:session:2",
    ]
    assert source == {"type": "message", "role": "user", "content": "hello"}


def test_envelope_ids_cannot_be_spoofed_by_event_payload(s09, tmp_path: Path) -> None:
    transcript = s09.JSONLTranscript(tmp_path / "session.jsonl")

    with pytest.raises(s09.TranscriptValidationError, match="reserved envelope"):
        transcript.append(
            {
                "type": "message",
                "role": "user",
                "content": "hello",
                "event_id": "transcript:other-session:99",
            }
        )

    assert transcript.count_lines() == 0


def test_replay_state_is_derived_not_persisted_runtime_state(s09, tmp_path: Path) -> None:
    transcript = s09.JSONLTranscript(tmp_path / "session.jsonl")
    transcript.append({"type": "message", "role": "user", "content": "fix it"})
    transcript.append({"type": "reasoning", "content": "inspect first"})
    transcript.append({"type": "ai-title", "title": "Fix issue"})
    state = transcript.replay_state()

    assert isinstance(state, s09.ReplayState)
    assert state.messages == [{"role": "user", "content": "fix it"}]
    assert state.title == "Fix issue"
    assert state.reasoning_count == 1
    assert state.next_sequence == 4
    assert "messages" not in transcript.path.read_text()  # no runtime snapshot event


def test_fresh_instance_replays_then_continues_sequence(s09, tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    s09.JSONLTranscript(path).append({"type": "message", "role": "user", "content": "one"})
    replacement = s09.JSONLTranscript(path)
    assert replacement.replay_state().next_sequence == 2
    replacement.append({"type": "message", "role": "assistant", "content": "two"})
    assert [event["sequence"] for event in replacement._read_all_events()] == [1, 2]


@pytest.mark.parametrize("valid_count", [0, 1])
@pytest.mark.parametrize("restart", [False, True])
def test_partial_tail_blocks_append_without_destroying_replay(s09, tmp_path, monkeypatch, valid_count, restart):
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    if valid_count:
        transcript.append({"type": "message", "role": "user", "content": "saved"})
    with path.open("ab") as handle:
        handle.write(b'{"type":"message","content":"unfinished')
    before = path.read_bytes()
    if restart:
        transcript = s09.JSONLTranscript(path)
    state = transcript.replay_state()
    assert state.ignored_partial_tail
    assert state.total_events == valid_count

    def forbidden_open(*args, **kwargs):
        raise AssertionError("partial tail must be rejected before opening for append")

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "open", forbidden_open)
        for _ in range(2):
            with pytest.raises(s09.TranscriptCorruptionError, match="partial tail"):
                transcript.append({"type": "message", "role": "user", "content": "new"})
    assert path.read_bytes() == before
    recovered = s09.JSONLTranscript(path).replay_state()
    assert recovered == state


def test_append_detects_tail_without_prior_replay(s09, tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text('{"type":', encoding="utf-8")
    with pytest.raises(s09.TranscriptCorruptionError, match="partial tail"):
        s09.JSONLTranscript(path).append({"type": "message", "role": "user", "content": "new"})
    assert path.read_text() == '{"type":'


def test_partial_tail_flag_is_reset_when_file_is_absent(s09, tmp_path):
    path = tmp_path / "session.jsonl"
    path.write_text('{"type":', encoding="utf-8")
    transcript = s09.JSONLTranscript(path)
    assert transcript.replay_state().ignored_partial_tail
    # Simulate explicit caller removal, not automatic repair by the transcript.
    path.unlink()
    assert not transcript.replay_state().ignored_partial_tail
    transcript.append({"type": "message", "role": "user", "content": "new"})
    assert transcript.replay_state().next_sequence == 2


def test_memory_candidate_is_explicit_and_keeps_exact_transcript_source(s09, tmp_path: Path) -> None:
    path = tmp_path / "session-42.jsonl"
    transcript = s09.JSONLTranscript(path)
    transcript.append(
        {
            "type": "message",
            "role": "user",
            "content": "Use SQLite WAL for local persistence.",
        }
    )
    transcript.append({"type": "reasoning", "content": "This may be durable."})

    candidate = transcript.select_memory_candidate(
        "transcript:session-42:1",
        summary="Selected SQLite WAL for local persistence.",
        reason="Explicit architecture decision confirmed by the user.",
    )

    assert candidate.source_id == "transcript:session-42:1"
    assert candidate.session_id == "session-42"
    assert candidate.sequence == 1
    assert candidate.event_type == s09.TYPE_MESSAGE
    assert candidate.source_type == "transcript"
    assert candidate.source_metadata() == {
        "source_id": "transcript:session-42:1",
        "source_type": "transcript",
        "title": "session-42 event 1",
        "captured_at": candidate.captured_at,
    }
    assert not hasattr(candidate, "content")  # source body stays in the transcript


def test_memory_selection_rejects_metadata_tool_output_and_unknown_ids(s09, tmp_path: Path) -> None:
    transcript = s09.JSONLTranscript(tmp_path / "session.jsonl")
    transcript.append({"type": "reasoning", "content": "private chain of thought"})
    transcript.append(
        {
            "type": "function_call_result",
            "callId": "call-1",
            "output": {"content": "x" * 20_000},
        }
    )

    for event_id in ("transcript:session:1", "transcript:session:2"):
        with pytest.raises(s09.MemorySelectionError, match="not eligible"):
            transcript.select_memory_candidate(
                event_id,
                summary="Should not be promoted.",
                reason="Negative contract test.",
            )

    with pytest.raises(s09.MemorySelectionError, match="unknown transcript event"):
        transcript.select_memory_candidate(
            "transcript:session:99",
            summary="Missing source.",
            reason="Negative contract test.",
        )
    with pytest.raises(s09.MemorySelectionError, match="summary"):
        transcript.select_memory_candidate(
            "transcript:session:1",
            summary=" ",
            reason="Negative contract test.",
        )


def test_prompt_replay_bound_does_not_define_memory_retention(s09, tmp_path: Path) -> None:
    transcript = s09.JSONLTranscript(tmp_path / "session.jsonl")
    transcript.append({"type": "message", "role": "user", "content": "durable decision"})
    transcript.append({"type": "message", "role": "assistant", "content": "recent reply"})

    assert transcript.replay(max_items=1) == [
        {"role": "assistant", "content": "recent reply"}
    ]
    candidate = transcript.select_memory_candidate(
        "transcript:session:1",
        summary="Durable decision.",
        reason="Selected independently of the prompt replay window.",
    )
    assert candidate.sequence == 1


def test_only_unterminated_corrupt_tail_is_ignored(s09, tmp_path: Path) -> None:
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    transcript.append({"type": "message", "role": "user", "content": "safe"})
    with path.open("ab") as handle:
        handle.write(b'{"type":')
    state = transcript.replay_state()
    assert state.ignored_partial_tail is True
    assert state.total_events == 1


def test_complete_corrupt_record_and_sequence_gap_fail_closed(s09, tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.jsonl"
    corrupt.write_text("{broken}\n", encoding="utf-8")
    with pytest.raises(s09.TranscriptCorruptionError, match="complete JSON"):
        s09.JSONLTranscript(corrupt).replay_state()

    gap = tmp_path / "gap.jsonl"
    gap.write_text(json.dumps({"sequence": 2, "type": "message"}) + "\n", encoding="utf-8")
    with pytest.raises(s09.TranscriptCorruptionError, match="expected sequence 1"):
        s09.JSONLTranscript(gap).replay_state()
