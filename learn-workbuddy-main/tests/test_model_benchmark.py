from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_model_benchmark_dry_run_writes_matrix_without_secrets(root: Path, tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    env["DEEPSEEK_API_KEY"] = "sk-test-deepseek"
    env["OPENAI_CHAT_API_KEY"] = "sk-test-gateway"
    env["OPENAI_CHAT_BASE_URL"] = "http://127.0.0.1:8080/v1"
    env["OPENAI_CHAT_MODEL"] = "gpt-test"

    out_dir = tmp_path / "bench"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/model_benchmark.py",
            "--providers",
            "deepseek",
            "openai-chat",
            "--max-lessons",
            "3",
            "--output",
            str(out_dir),
            "--dry-run",
        ],
        cwd=root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
    )

    assert result.returncode == 0, result.stdout
    stats = json.loads((out_dir / "latest-stats.json").read_text(encoding="utf-8"))
    case_ids = {case["case_id"] for case in stats["cases"]}

    assert "deepseek::mini" in case_ids
    assert "deepseek::full" in case_ids
    assert "openai-chat::mini" in case_ids
    assert "openai-chat::full" in case_ids
    assert any(case_id.startswith("deepseek::lesson::s01") for case_id in case_ids)
    assert any(case_id.startswith("deepseek::lesson::s03") for case_id in case_ids)
    assert any(case_id.startswith("openai-chat::lesson::s01") for case_id in case_ids)
    assert any(case_id.startswith("openai-chat::lesson::s03") for case_id in case_ids)
    assert stats["summary"]["total"] == 10
    assert "sk-test" not in (out_dir / "latest-stats.json").read_text(encoding="utf-8")
    assert "sk-test" not in (out_dir / "latest.md").read_text(encoding="utf-8")

    for case in stats["cases"]:
        trace_path = Path(case["trace_path"])
        assert trace_path.exists(), case["case_id"]
        assert trace_path.read_text(encoding="utf-8").strip(), case["case_id"]
        assert case["trace_events"] >= 1


def test_model_benchmark_discovers_all_lesson_scripts(root: Path) -> None:
    sys.path.insert(0, str(root))
    try:
        from scripts import model_benchmark as bm
    finally:
        sys.path.remove(str(root))

    lessons = bm.discover_lessons()
    names = [lesson.chapter for lesson in lessons]

    assert "s01_agent_loop" in names
    assert "s24_comprehensive" in names
    assert "s03_deferred_loading" in names
    assert "s08_model_routing" in names
    assert "s09_jsonl_transcript" in names
    assert "s13_output_externalization" in names
    assert len(lessons) == 24


def test_model_benchmark_builds_lesson_eval_cases_for_every_provider(root: Path) -> None:
    sys.path.insert(0, str(root))
    try:
        from scripts import model_benchmark as bm
    finally:
        sys.path.remove(str(root))

    cases = bm.build_cases(["deepseek", "openai-chat"])
    lesson_cases = [case for case in cases if case.kind == "lesson"]

    assert sum(1 for case in lesson_cases if case.provider == "deepseek") == 24
    assert sum(1 for case in lesson_cases if case.provider == "openai-chat") == 24
    assert all("--eval" in case.command for case in lesson_cases)


def test_model_benchmark_uses_command_script_for_s22(root: Path) -> None:
    sys.path.insert(0, str(root))
    try:
        from scripts import model_benchmark as bm
    finally:
        sys.path.remove(str(root))

    cases = bm.build_cases(["deepseek"])
    s22 = next(case for case in cases if case.case_id == "deepseek::lesson::s22_automation_scheduler")

    assert s22.stdin is None
    assert "--eval" in s22.command
