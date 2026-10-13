"""s09: append must refuse unless the transcript file ends with the byte b"\\n".

Contract under test (s09 README §损坏处理为什么只放过 partial tail, append()
comment in code.py): append() writes exactly one ``json.dumps(...) + "\\n"``
record, and an append must never turn a replayable log into one that replay
rejects. Callers keep the old file and open a new transcript; append() does not
truncate or pad a newline.

Today ``_read_all_events`` only sets ``_ignored_partial_tail`` when the last
line fails ``json.loads`` and lacks ``\\n``. A last line that is complete JSON
but lacks ``\\n`` (e.g. after a short write of ``encoded[:-1]``) replays as a
healthy log, so O_APPEND glues the next record onto the same line and the next
replay raises ``invalid complete JSON record``.

Expected fix shape (locked here): the termination check is made on the raw
bytes (not on ``str.splitlines()``/``read_text()`` lines, which also break on
``\\r``, ``\\x0b``, ``\\x85``, U+2028 ...). Replay results stay unchanged:
the complete last record is still counted and ``ignored_partial_tail`` stays
False because nothing was ignored.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REFUSAL = "partial tail|newline|unterminated"


@pytest.fixture(scope="module")
def s09():
    name = "s09_unterminated_complete_line_test_module"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "s09_jsonl_transcript" / "code.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


def _assert_single_saved_record(s09, path: Path) -> None:
    state = s09.JSONLTranscript(path).replay_state()
    assert state.total_events == 1
    assert state.messages == [{"role": "user", "content": "saved"}]
    # Nothing was ignored: the complete record is counted.
    assert state.ignored_partial_tail is False


def _refuse_append_and_keep_bytes(s09, path: Path) -> None:
    before = path.read_bytes()
    with pytest.raises(s09.TranscriptCorruptionError, match=REFUSAL):
        s09.JSONLTranscript(path).append(
            {"type": "message", "role": "assistant", "content": "new"}
        )
    assert path.read_bytes() == before
    _assert_single_saved_record(s09, path)


def _saved_log(s09, tmp_path: Path) -> tuple[Path, bytes]:
    path = tmp_path / "session.jsonl"
    s09.JSONLTranscript(path).append(
        {"type": "message", "role": "user", "content": "saved"}
    )
    raw = path.read_bytes()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    return path, raw


def test_append_refuses_complete_json_last_line_without_trailing_newline(
    s09, tmp_path: Path
) -> None:
    """Bug repro: complete JSON record whose trailing newline was lost."""
    path, raw = _saved_log(s09, tmp_path)
    path.write_bytes(raw[:-1])
    assert isinstance(json.loads(path.read_text(encoding="utf-8")), dict)

    _assert_single_saved_record(s09, path)
    _refuse_append_and_keep_bytes(s09, path)


def test_short_write_missing_newline_then_retry_append_must_refuse(
    s09, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bug repro: append itself creates this state via a short write; retry must refuse."""
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    real_write = s09.os.write
    calls = {"n": 0}

    def write_all_but_newline(fd: int, data: bytes) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            written = real_write(fd, data[:-1])
            assert written == len(data) - 1
            return written
        return real_write(fd, data)

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "write", write_all_but_newline)
        with pytest.raises(OSError, match="short transcript write"):
            transcript.append({"type": "message", "role": "user", "content": "saved"})

    before = path.read_bytes()
    assert before and not before.endswith(b"\n")
    assert isinstance(json.loads(before.decode("utf-8")), dict)

    _assert_single_saved_record(s09, path)
    # Natural retry on the same object and on a replacement runtime.
    for writer in (transcript, s09.JSONLTranscript(path)):
        with pytest.raises(s09.TranscriptCorruptionError, match=REFUSAL):
            writer.append({"type": "message", "role": "assistant", "content": "retry"})
        assert path.read_bytes() == before
    _assert_single_saved_record(s09, path)


def test_append_refuses_complete_json_last_line_ending_with_cr(
    s09, tmp_path: Path
) -> None:
    """The check is on raw bytes: a final b"\\r" is not the writer's b"\\n" boundary.

    read_text() maps a lone \\r to \\n and splitlines() breaks on it, so a
    line-based check would treat this tail as terminated.
    """
    path, raw = _saved_log(s09, tmp_path)
    path.write_bytes(raw[:-1] + b"\r")

    _assert_single_saved_record(s09, path)
    _refuse_append_and_keep_bytes(s09, path)


@pytest.mark.parametrize(
    "tail",
    ["   ", "\t", "\u00a0", "\u3000"],
    ids=["spaces", "tab", "nbsp", "ideographic-space"],
)
def test_append_refuses_whitespace_only_unterminated_tail(
    s09, tmp_path: Path, tail: str
) -> None:
    """Whitespace-only last line without b"\\n" is refused too (single byte rule).

    Replay skips it (``not line.strip()``), but appending would prefix the next
    record with it; ``json.loads`` rejects U+00A0 / U+3000, so for those tails
    today's append makes the log unreplayable.
    """
    path, raw = _saved_log(s09, tmp_path)
    path.write_bytes(raw + tail.encode("utf-8"))

    _assert_single_saved_record(s09, path)
    _refuse_append_and_keep_bytes(s09, path)


@pytest.mark.parametrize("initial", [None, b""], ids=["missing", "empty"])
def test_append_allowed_for_missing_or_empty_file(
    s09, tmp_path: Path, initial: bytes | None
) -> None:
    """Control: no bytes means no unterminated tail."""
    path = tmp_path / "session.jsonl"
    if initial is not None:
        path.write_bytes(initial)
    transcript = s09.JSONLTranscript(path)
    transcript.append({"type": "message", "role": "user", "content": "saved"})
    _assert_single_saved_record(s09, path)


def test_append_still_works_when_file_ends_with_newline(s09, tmp_path: Path) -> None:
    """Control: a clean durable boundary (trailing newline) still appends."""
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    transcript.append({"type": "message", "role": "user", "content": "a"})
    assert path.read_bytes().endswith(b"\n")

    transcript.append({"type": "message", "role": "assistant", "content": "b"})
    state = transcript.replay_state()
    assert state.total_events == 2
    assert state.messages == [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
    ]
    assert state.ignored_partial_tail is False
