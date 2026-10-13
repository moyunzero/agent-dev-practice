"""Behavior tests for S07's logical-session/runtime boundary.

The tests stay offline and replace the HTTP listener with a tiny fake.  They
exercise the lifecycle contract rather than relying on network availability:

* create allocates one logical id and one runtime generation;
* close releases runtime resources but keeps the record and transcript;
* resume creates a fresh runtime for the same logical session id; and
* forget is the separate, explicit history-deletion operation.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s07():
    """Import the standalone chapter with the repository's offline SDK stub."""

    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    old_model = os.environ.get("MODEL_ID")
    os.environ["MODEL_ID"] = "offline-test-model"
    module_name = "s07_session_management_test_module"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            ROOT / "s07_session_management" / "code.py",
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


@pytest.fixture()
def fake_transport(monkeypatch: pytest.MonkeyPatch, s07):
    """Give each runtime a deterministic fake port without opening a socket."""

    class FakeSessionHTTPServer:
        next_port = 31_000

        def __init__(self, _address, session) -> None:
            type(self).next_port += 1
            self.session = session
            self.server_address = ("127.0.0.1", type(self).next_port)
            self.closed = False

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            self.closed = True

    monkeypatch.setattr(s07, "SessionHTTPServer", FakeSessionHTTPServer)
    return FakeSessionHTTPServer


def test_create_separates_logical_record_from_runtime_resources(
    s07, fake_transport, tmp_path: Path
) -> None:
    manager = s07.SessionManager()
    session_id = manager.create_session(
        str(tmp_path), mode=s07.MODE_PLAN, backend="pty", title="Lifecycle"
    )

    runtime = manager.get_session(session_id)
    record = manager.load_record(session_id)
    assert runtime is not None
    assert record.status == s07.STATE_IDLE
    assert record.runtime_generation == 1
    assert record.cwd == str(tmp_path.resolve())
    assert record.mode == s07.MODE_PLAN
    assert runtime.port == 31_001
    assert not hasattr(record, "port")
    assert not hasattr(record, "_http_server")

    manager.shutdown_all()


def test_turn_state_is_published_and_transcript_survives_close_resume(
    s07, fake_transport, tmp_path: Path
) -> None:
    manager = s07.SessionManager()
    session_id = manager.create_session(str(tmp_path))
    first_runtime = manager.get_session(session_id)
    assert first_runtime is not None
    first_port = first_runtime.port

    def fake_provider_call(user_message: str) -> str:
        assert first_runtime.status == s07.STATE_RUNNING
        first_runtime.record.messages.extend(
            [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": "offline answer"},
            ]
        )
        first_runtime._publish()
        return "offline answer"

    first_runtime._call_provider = fake_provider_call
    assert first_runtime.run_agent_loop("hello") == "offline answer"
    assert first_runtime.status == s07.STATE_IDLE

    assert manager.close_session(session_id) is True
    closed = manager.load_record(session_id)
    assert manager.get_session(session_id) is None
    assert closed.status == s07.STATE_CLOSED
    assert len(closed.messages) == 2

    assert manager.resume_session(session_id) == session_id
    resumed_runtime = manager.get_session(session_id)
    resumed = manager.load_record(session_id)
    assert resumed_runtime is not None
    assert resumed_runtime is not first_runtime
    assert resumed_runtime.port != first_port
    assert resumed.status == s07.STATE_IDLE
    assert resumed.runtime_generation == 2
    assert resumed.messages == closed.messages

    manager.shutdown_all()


def test_new_manager_can_resume_shared_store_without_reusing_runtime(
    s07, fake_transport, tmp_path: Path
) -> None:
    store = s07.InMemorySessionStore()
    first_manager = s07.SessionManager(store)
    first_id = first_manager.create_session(str(tmp_path))
    first_runtime = first_manager.get_session(first_id)
    first_manager.shutdown_all()

    replacement_manager = s07.SessionManager(store)
    replacement_manager.resume_session(first_id)
    replacement_runtime = replacement_manager.get_session(first_id)
    assert replacement_runtime is not None
    assert replacement_runtime is not first_runtime
    assert replacement_manager.load_record(first_id).runtime_generation == 2

    second_id = replacement_manager.create_session(str(tmp_path))
    assert second_id == "sess_0002"
    replacement_manager.shutdown_all()


def test_resume_rejects_duplicate_live_runtime(s07, fake_transport, tmp_path: Path) -> None:
    manager = s07.SessionManager()
    session_id = manager.create_session(str(tmp_path))

    with pytest.raises(s07.SessionAlreadyRunningError):
        manager.resume_session(session_id)

    manager.shutdown_all()


def test_close_is_idempotent_but_forget_is_explicit(
    s07, fake_transport, tmp_path: Path
) -> None:
    manager = s07.SessionManager()
    session_id = manager.create_session(str(tmp_path))

    with pytest.raises(s07.SessionLifecycleError, match="close session"):
        manager.forget_session(session_id)

    assert manager.close_session(session_id) is True
    assert manager.close_session(session_id) is False
    assert manager.load_record(session_id).status == s07.STATE_CLOSED
    assert manager.forget_session(session_id) is True
    with pytest.raises(s07.SessionNotFoundError):
        manager.load_record(session_id)


@pytest.mark.parametrize(
    ("mode", "backend"),
    [("invalid", "pipe"), ("craft", "socket")],
)
def test_create_validates_runtime_options(
    s07, fake_transport, tmp_path: Path, mode: str, backend: str
) -> None:
    manager = s07.SessionManager()

    with pytest.raises(ValueError):
        manager.create_session(str(tmp_path), mode=mode, backend=backend)


def test_provider_failure_is_recorded_and_can_be_resumed(
    s07, fake_transport, tmp_path: Path
) -> None:
    manager = s07.SessionManager()
    session_id = manager.create_session(str(tmp_path))
    runtime = manager.get_session(session_id)
    assert runtime is not None

    def fail_provider(_message: str) -> str:
        raise RuntimeError("provider unavailable")

    runtime._call_provider = fail_provider
    with pytest.raises(RuntimeError, match="provider unavailable"):
        runtime.run_agent_loop("hello")

    failed = manager.load_record(session_id)
    assert failed.status == s07.STATE_ERROR
    assert failed.last_error == "provider unavailable"

    manager.close_session(session_id)
    manager.resume_session(session_id)
    recovered = manager.load_record(session_id)
    assert recovered.status == s07.STATE_IDLE
    assert recovered.last_error is None
    assert recovered.runtime_generation == 2
    manager.shutdown_all()


def test_late_provider_result_cannot_overwrite_closed_record(
    s07, fake_transport, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A synchronous SDK response may return after close has released runtime."""

    provider_started = threading.Event()
    release_provider = threading.Event()

    class BlockingMessages:
        def create(self, **_kwargs):
            provider_started.set()
            assert release_provider.wait(timeout=3)
            text = SimpleNamespace(type="text", text="late answer")
            return SimpleNamespace(stop_reason="end_turn", content=[text])

    class BlockingClient:
        def __init__(self) -> None:
            self.messages = BlockingMessages()

    monkeypatch.setattr(s07, "Anthropic", lambda **_kwargs: BlockingClient())

    manager = s07.SessionManager()
    session_id = manager.create_session(str(tmp_path))
    runtime = manager.get_session(session_id)
    assert runtime is not None
    output: list[str] = []

    turn = threading.Thread(target=lambda: output.append(runtime.run_agent_loop("hello")))
    turn.start()
    assert provider_started.wait(timeout=3)
    manager.close_session(session_id)
    assert manager.load_record(session_id).status == s07.STATE_CLOSED

    release_provider.set()
    turn.join(timeout=3)
    assert not turn.is_alive()
    retained = manager.load_record(session_id)
    assert retained.status == s07.STATE_CLOSED
    assert retained.messages == []
    assert output == ["(turn discarded because the session runtime closed)"]
