"""Smoke test for the full-tour example.

The tour is the repo's most integration-heavy artifact: provider adapter,
session, memory, tool dispatch, permission denial, externalization, JSONL
recovery, HTTP run, and audit — all in one run. This test pins that the
offline path stays green end to end, exits 0, verifies the audit chain,
and emits a manifest whose per-stage flags are all truthy.

Kept offline-only: no key, no network beyond loopback HTTP, deterministic.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


def load_full_tour(root: Path):
    """Load the example as a module without giving it package-only behavior."""

    module_name = "test_full_tour_example"
    spec = importlib.util.spec_from_file_location(
        module_name,
        root / "examples" / "full_tour" / "code.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load full-tour example")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_full_tour_offline_runs_green(root: Path, tmp_path: Path) -> None:
    home = tmp_path / "tour-home"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    # Force offline regardless of any ambient keys in the runner.
    env["PROVIDER"] = "offline"
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MODEL_ID"):
        env.pop(key, None)

    result = subprocess.run(
        [sys.executable, "examples/full_tour/code.py", "--home", str(home), "--provider", "offline"],
        cwd=root,
        env=env,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout[-3000:]

    manifest_path = home / "full_tour_manifest.json"
    assert manifest_path.exists(), "tour did not write its manifest"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["provider"] == "offline"
    stages = manifest["stages"]
    assert stages["tool_dispatch"] is True
    assert stages["provider_probe"] is True
    assert stages["provider_tool_calls"] >= 1
    assert stages["memory_recall_hits"] >= 1
    assert stages["memory_context_selected"] >= 1
    assert stages["memory_context_injected"] is True
    assert stages["memory_context_chars"] > 0
    assert stages["permission_denied"] is True
    assert stages["externalized"] is True
    assert stages["http_run"] is True
    assert stages["audit_verified"] is True
    assert stages["transcript_events"] >= 2
    assert stages["audit_entries"] >= 5

    # Every artifact the manifest points to must actually exist on disk.
    for name, path in manifest["artifacts"].items():
        assert Path(path).exists(), f"missing artifact {name}: {path}"

    # The exported context is the inspectable boundary between chapter recall
    # and the provider loop.  Stable IDs preserve enough provenance to explain
    # why a memory entered the prompt without exposing the backing store.
    recalled_context = Path(manifest["artifacts"]["recalled_context"]).read_text(encoding="utf-8")
    assert "<recalled_memory" in recalled_context
    assert "memory_id=" in recalled_context
    assert "source_id=" in recalled_context
    assert 'authority="workspace_override"' in recalled_context


def test_provider_probe_sends_selected_memory_in_system_request(root: Path, tmp_path: Path) -> None:
    full_tour = load_full_tour(root)

    class RecordingProvider(full_tour.P.OfflineMockProvider):
        def __init__(self) -> None:
            super().__init__()
            self.system_requests: list[str] = []

        def create(self, request):
            self.system_requests.append(request.system)
            return super().create(request)

    config = full_tour.HarnessConfig(root_dir=tmp_path / "probe-home")
    config.ensure_dirs()
    storage = full_tour.Storage(config)
    session = storage.create_session(cwd=str(root), title="memory injection probe")
    provider = RecordingProvider()
    selected_context = (
        '<recalled_memory user_scope="scope" selected="1">\n'
        '<memory_hit memory_id="memory-1" source_id="source-1">fact</memory_hit>\n'
        "</recalled_memory>"
    )

    result = full_tour.provider_probe(
        provider,
        session,
        storage,
        full_tour.ToolRegistry(config, storage),
        full_tour.AuditLog(config),
        full_tour.EventBus(),
        memory_context=selected_context,
    )

    assert result["ok"] is True
    assert result["memory_context_injected"] is True
    assert provider.system_requests
    assert all(selected_context in system for system in provider.system_requests)
