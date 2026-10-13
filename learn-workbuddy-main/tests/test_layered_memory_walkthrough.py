"""End-to-end contracts for the keyless layered-memory walkthrough."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_layered_memory_walkthrough_is_keyless_and_restart_safe(
    root: Path,
    tmp_path: Path,
) -> None:
    home = tmp_path / "layered-memory"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    # The walkthrough must exercise chapter storage contracts without falling
    # through to any provider client, regardless of the developer environment.
    for key in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "MODEL_ID",
    ):
        env.pop(key, None)

    result = subprocess.run(
        [
            sys.executable,
            "examples/layered_memory_walkthrough/code.py",
            "--home",
            str(home),
        ],
        cwd=root,
        env=env,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout[-4_000:]
    assert "RESULT: OK" in result.stdout
    assert "created -> unchanged; bob empty=True" in result.stdout
    assert "lease recovered=1" in result.stdout
    assert "referenced retained=1; expired orphan deleted=1" in result.stdout
    assert "durable preserved=True" in result.stdout
    assert "sources verified=2" in result.stdout

    manifest_path = home / "layered_memory_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert all(manifest["checks"].values())
    assert manifest["layers"]["transcript"]["events"] == 2
    assert manifest["layers"]["workspace"]["facts"] == 3
    assert manifest["layers"]["workspace"]["curated_entries"] == 1
    assert manifest["layers"]["workspace"]["distill"]["eligible"] == 2
    assert manifest["layers"]["user"] == {
        "preference_count": 1,
        "first_write": "created",
        "repeated_write": "unchanged",
        "other_user_preference_count": 0,
    }
    assert len(manifest["layers"]["recall"]["hits"]) == 1
    assert manifest["layers"]["recall"]["hits"][0]["source"]["source_id"] == (
        "transcript:memory-session:2"
    )

    # Memory receives bounded artifact metadata, never the externalized body.
    artifact_layer = manifest["layers"]["artifact"]
    artifact_reference = artifact_layer["reference"]
    assert "content" not in artifact_reference
    assert len(artifact_reference["content_sha256"]) == 64
    assert Path(artifact_reference["artifact_path"]).stat().st_size > 30_000
    lease_recovery = artifact_layer["lease_recovery"]
    assert lease_recovery["pending_transaction_ids"] == []
    assert lease_recovery["claims"][0]["reference_count"] == 1
    assert lease_recovery["states"][0]["phases"] == ["prepared", "committed"]
    assert str(home) not in json.dumps(lease_recovery, sort_keys=True)
    assert artifact_layer["cleanup"]["counts"] == {
        "deleted": 1,
        "retained_referenced": 1,
    }
    assert artifact_layer["orphan_resolution"]["status"] == "missing"
    assert all(
        "artifact_path" not in decision
        for decision in artifact_layer["cleanup"]["decisions"]
    )

    compaction = manifest["layers"]["compaction"]
    assert compaction["applied_layers"] == [
        "tool_result_truncation",
        "message_pruning",
        "conversation_summary",
    ]
    assert "workspace-decision-1" in compaction["durable_context"]
    assert "artifact:artifact-session:" in compaction["durable_context"]
    assert compaction["durable_context"].count("source_status=available") == 2
    assert "evidence_unavailable" not in compaction["durable_context"]
    assert "migration is complete" not in compaction["durable_context"].lower()
    source_resolutions = compaction["source_resolutions"]
    assert [item["status"] for item in source_resolutions] == [
        "available",
        "available",
    ]
    assert {item["source_type"] for item in source_resolutions} == {
        "transcript",
        "artifact",
    }
    assert all(len(item["evidence_sha256"]) == 64 for item in source_resolutions)
    assert all("excerpt" not in item for item in source_resolutions)

    # Every advertised durable owner must remain inspectable after the fresh
    # instances used by the walkthrough have reconstructed their views.
    for artifact_path in manifest["artifacts"].values():
        path = Path(artifact_path)
        assert path.exists()
        assert path.is_relative_to(home)
