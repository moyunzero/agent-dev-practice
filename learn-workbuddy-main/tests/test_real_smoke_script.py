from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_real_smoke(root: Path):
    spec = importlib.util.spec_from_file_location(
        "run_real_smoke", root / "scripts" / "run_real_smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_real_smoke_has_full_tour_target_for_gateway_providers(root: Path) -> None:
    mod = _load_real_smoke(root)

    assert {"mini", "s01", "s24", "full", "all-lessons"} <= set(mod.TARGETS)


def test_openai_chat_runs_lesson_eval_entrypoints(root: Path, monkeypatch) -> None:
    mod = _load_real_smoke(root)
    calls: list[tuple[list[str], str | None, int, dict[str, str] | None]] = []

    def fake_run(cmd, stdin=None, timeout=120, env=None):
        calls.append((cmd, stdin, timeout, env))
        return 0

    monkeypatch.setattr(mod, "_run", fake_run)

    code = mod.smoke_lesson("s01_agent_loop/code.py", "openai-chat")

    assert code == 0
    cmd, stdin, timeout, env = calls[0]
    assert "--eval" in cmd
    assert "--provider" in cmd
    assert "openai-chat" in cmd
    assert "--trace" in cmd
    assert stdin is None
    assert timeout == 240
    assert env and "MINI_WORKBUDDY_HOME" in env


def test_openai_chat_runs_all_lesson_eval_entrypoints(root: Path, monkeypatch) -> None:
    mod = _load_real_smoke(root)
    calls: list[tuple[list[str], str | None, int, dict[str, str] | None]] = []

    monkeypatch.setattr(mod, "_model_lesson_targets", lambda: [
        root / "s01_agent_loop" / "code.py",
        root / "s03_deferred_loading" / "code.py",
    ])
    monkeypatch.setattr(mod, "_run", lambda cmd, stdin=None, timeout=120, env=None: calls.append((cmd, stdin, timeout, env)) or 0)

    code = mod.smoke_all_lessons("openai-chat")

    assert code == 0
    assert len(calls) == 2
    assert all("--eval" in call[0] for call in calls)
    assert all("openai-chat" in call[0] for call in calls)
