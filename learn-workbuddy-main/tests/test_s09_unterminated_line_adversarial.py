"""复核末行缺换行修复的状态重置、写入边界与读取兼容性。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REFUSAL = "partial tail|newline|unterminated"
SAVED = b'{"type":"message","role":"user","content":"saved"}'


@pytest.fixture(scope="module")
def s09():
    name = "s09_unterminated_line_adversarial_module"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "s09_jsonl_transcript" / "code.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(name, None)


@pytest.mark.parametrize(
    ("replacement", "old_count"),
    [(None, 0), (b"", 0), (SAVED + b"\n", 1), (b"\n", 0), (b" \t\n", 0)],
    ids=["missing", "empty", "valid", "blank-line", "whitespace-line"],
)
def test_missing_newline_flag_resets_on_each_read(
    s09, tmp_path: Path, replacement: bytes | None, old_count: int
) -> None:
    """攻击旧标志残留，以及只在追加时清除标志而读取仍保留旧状态的实现。"""
    path = tmp_path / "session.jsonl"
    path.write_bytes(SAVED)
    transcript = s09.JSONLTranscript(path)
    state = transcript.replay_state()
    assert state.total_events == 1
    assert state.ignored_partial_tail is False
    assert transcript._missing_final_newline is True

    # 文件改变由调用方模拟，日志对象自身不得自动修复。
    if replacement is None:
        path.unlink()
    else:
        path.write_bytes(replacement)

    state = transcript.replay_state()
    assert state.total_events == old_count
    assert state.next_sequence == old_count + 1
    assert state.ignored_partial_tail is False
    assert transcript._missing_final_newline is False
    assert transcript._ignored_partial_tail is False

    transcript.append({"type": "message", "role": "assistant", "content": "new"})
    events = transcript._read_all_events()
    assert [event["sequence"] for event in events] == list(range(1, old_count + 2))
    assert events[-1]["content"] == "new"
    assert path.read_bytes().startswith(replacement or b"")
    assert path.read_bytes().endswith(b"\n")


def test_complete_unterminated_tail_is_refused_before_open(
    s09, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """攻击先打开追加描述符才拒绝，以及拒绝后改变完整记录或回放状态的实现。"""
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    transcript.append({"type": "message", "role": "user", "content": "saved"})
    transcript.append({"type": "ai-title", "title": "保留标题"})
    transcript.append({"type": "file-history-snapshot", "path": "note.txt", "hash": "demo"})
    raw = path.read_bytes()
    path.write_bytes(raw[:-1])
    before = path.read_bytes()
    expected_events = transcript._read_all_events()
    expected_state = transcript.replay_state()
    expected_recovery = transcript.recover()
    assert expected_state.total_events == 3
    assert expected_state.next_sequence == 4
    assert expected_state.ignored_partial_tail is False
    assert expected_state.title == "保留标题"
    assert expected_state.file_snapshots == [{"path": "note.txt", "hash": "demo"}]

    def forbidden_open(*args, **kwargs):
        raise AssertionError("必须在打开追加描述符前拒绝")

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "open", forbidden_open)
        for writer in (transcript, s09.JSONLTranscript(path)):
            with pytest.raises(s09.TranscriptCorruptionError, match=REFUSAL):
                writer.append({"type": "message", "role": "assistant", "content": "new"})

    assert path.read_bytes() == before
    assert transcript._read_all_events() == expected_events
    assert transcript.replay_state() == expected_state
    assert transcript.recover() == expected_recovery


def test_short_write_inside_json_keeps_partial_tail_priority(
    s09, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """攻击截在 JSON 中间后的重试，要求两个标志同时为真时仍报告残缺尾部。"""
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    transcript.append({"type": "message", "role": "user", "content": "saved"})
    saved = path.read_bytes()
    real_write = s09.os.write

    def write_partial_json(fd: int, data: bytes) -> int:
        cut = data.index(b'"content"') + len(b'"content"')
        return real_write(fd, data[:cut])

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "write", write_partial_json)
        with pytest.raises(OSError, match="short transcript write"):
            transcript.append({"type": "message", "role": "assistant", "content": "unfinished"})

    before = path.read_bytes()
    assert before.startswith(saved) and len(before) > len(saved)
    assert not before.endswith(b"\n")
    state = transcript.replay_state()
    assert state.total_events == 1
    assert state.messages == [{"role": "user", "content": "saved"}]
    assert state.ignored_partial_tail is True
    assert transcript._missing_final_newline is True

    def forbidden_open(*args, **kwargs):
        raise AssertionError("残缺尾部不得再次打开写入")

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "open", forbidden_open)
        for writer in (transcript, s09.JSONLTranscript(path)):
            with pytest.raises(s09.TranscriptCorruptionError, match="after partial tail"):
                writer.append({"type": "message", "role": "assistant", "content": "retry"})

    assert path.read_bytes() == before
    assert transcript.replay_state() == state


def test_short_write_inside_utf8_preserves_decode_failure(
    s09, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """攻击多字节字符被截断的短写，要求保留原读取异常且重试不触碰文件。"""
    path = tmp_path / "session.jsonl"
    transcript = s09.JSONLTranscript(path)
    real_write = s09.os.write

    def write_partial_utf8(fd: int, data: bytes) -> int:
        cut = data.index("中".encode("utf-8")) + 1
        return real_write(fd, data[:cut])

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "write", write_partial_utf8)
        with pytest.raises(OSError, match="short transcript write"):
            transcript.append({"type": "message", "role": "user", "content": "中文"})

    before = path.read_bytes()
    with pytest.raises(UnicodeDecodeError) as original:
        path.read_text(encoding="utf-8")

    def forbidden_open(*args, **kwargs):
        raise AssertionError("解码失败后不得打开追加描述符")

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "open", forbidden_open)
        for writer in (transcript, s09.JSONLTranscript(path)):
            with pytest.raises(UnicodeDecodeError) as replay_error:
                writer.replay_state()
            assert str(replay_error.value) == str(original.value)
            with pytest.raises(UnicodeDecodeError) as append_error:
                writer.append({"type": "message", "role": "assistant", "content": "retry"})
            assert str(append_error.value) == str(original.value)
            assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("broken", "message"),
    [(b"{broken}", "invalid complete JSON"), (b'{"sequence":2}', "expected sequence 1")],
    ids=["malformed", "sequence-gap"],
)
def test_final_newline_does_not_hide_bad_penultimate_record(
    s09, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, broken: bytes, message: str
) -> None:
    """攻击只检查最后一个字节就放行、从而跳过倒数第二行损坏的实现。"""
    path = tmp_path / "session.jsonl"
    before = broken + b"\n" + SAVED + b"\n"
    path.write_bytes(before)
    transcript = s09.JSONLTranscript(path)
    with pytest.raises(s09.TranscriptCorruptionError, match=message):
        transcript.replay_state()

    def forbidden_open(*args, **kwargs):
        raise AssertionError("前行损坏时不得打开追加描述符")

    with monkeypatch.context() as patch:
        patch.setattr(s09.os, "open", forbidden_open)
        with pytest.raises(s09.TranscriptCorruptionError, match=message):
            transcript.append({"type": "message", "role": "assistant", "content": "new"})
    assert path.read_bytes() == before


def test_replay_preserves_crlf_boundary_and_lone_cr(s09, tmp_path: Path) -> None:
    """攻击遗漏通用换行转换，包括常见缓冲边界上的回车换行及孤立回车。"""
    path = tmp_path / "session.jsonl"
    title = b'{"type":"ai-title","title":"saved title"}'
    # 回车处于第八千一百九十二个字节，换行位于其后。
    before = SAVED + b" " * (8191 - len(SAVED)) + b"\r\n" + title + b"\r"
    path.write_bytes(before)
    transcript = s09.JSONLTranscript(path)
    state = transcript.replay_state()
    assert state.total_events == 2
    assert state.next_sequence == 3
    assert state.messages == [{"role": "user", "content": "saved"}]
    assert state.title == "saved title"
    assert state.ignored_partial_tail is False
    assert transcript.recover()["title"] == "saved title"

    with pytest.raises(s09.TranscriptCorruptionError, match=REFUSAL):
        transcript.append({"type": "message", "role": "assistant", "content": "new"})
    assert path.read_bytes() == before
    assert transcript.replay_state() == state

    # 孤立回车必须被规范化为换行，残缺 JSON 因此属于完整坏行。
    malformed = before + b'{"type":\r'
    path.write_bytes(malformed)
    with pytest.raises(s09.TranscriptCorruptionError, match="invalid complete JSON"):
        transcript.replay_state()
    assert path.read_bytes() == malformed
