"""Contract tests for the offline Memory resilience scorecard."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "examples" / "memory_resilience_eval" / "code.py"


def load_module():
    module_name = "memory_resilience_eval_test_module"
    spec = importlib.util.spec_from_file_location(module_name, CODE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_scorecard_exercises_every_memory_failure_boundary(tmp_path: Path) -> None:
    module = load_module()

    report = module.run_evaluation(tmp_path)

    assert report.passed is True
    assert report.summary == {"total": 5, "passed": 5, "failed": 0}
    results = {result.case_id: result for result in report.cases}
    assert set(results) == {
        "concurrent_duplicate_write",
        "id_collision",
        "scope_isolation",
        "corrupt_store",
        "restart_recall",
    }
    assert results["concurrent_duplicate_write"].evidence["durable_records"] == 1
    assert results["concurrent_duplicate_write"].evidence["created"] == 1
    assert results["id_collision"].evidence["rejected_error"] == (
        "RemoteMemoryDuplicateError"
    )
    assert results["scope_isolation"].evidence["rejected_error"] == (
        "RemoteMemoryScopeError"
    )
    assert results["corrupt_store"].evidence["rejected_error"] == (
        "RemoteMemoryCorruptionError"
    )
    assert results["restart_recall"].evidence["store_unchanged"] is True
    assert results["restart_recall"].evidence["provenance_preserved"] is True

    payload = json.loads(
        (tmp_path / "memory-resilience-report.json").read_text(encoding="utf-8")
    )
    assert payload == report.to_dict()


def test_unexpected_case_error_is_reported_without_aborting(tmp_path: Path) -> None:
    module = load_module()

    def broken_case(_chapter, _case_dir):
        raise RuntimeError("injected evaluator failure")

    report = module.evaluate_cases(
        module.load_memory_chapter(),
        tmp_path,
        cases=(
            module.CaseDefinition(
                case_id="broken_case",
                contract="Unexpected evaluator errors remain visible.",
                runner=broken_case,
            ),
        ),
    )

    assert report.passed is False
    assert report.summary == {"total": 1, "passed": 0, "failed": 1}
    assert report.cases[0].observed == "unexpected_exception"
    assert report.cases[0].evidence == {
        "error_type": "RuntimeError",
        "message": "injected evaluator failure",
    }


def test_cli_is_keyless_and_writes_the_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "cli-output"
    env = os.environ.copy()
    for name in (
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
    ):
        env.pop(name, None)

    result = subprocess.run(
        [sys.executable, str(CODE), "--output-dir", str(output_dir)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Memory resilience evaluation" in result.stdout
    assert "Passed: 5/5" in result.stdout
    assert "RESULT: OK" in result.stdout
    assert (output_dir / "memory-resilience-report.json").exists()
