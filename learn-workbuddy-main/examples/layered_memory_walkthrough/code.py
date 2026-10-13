#!/usr/bin/env python3
"""Keyless walkthrough for the repository's existing memory chapters.

The chapter files remain the authoritative implementations.  This example only
coordinates their public teaching contracts so readers can observe how one
piece of evidence moves through transcript selection, scoped memory, recall,
artifact externalization, compaction, and restart recovery.

No provider client is constructed and no API key or network access is needed.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


CHAPTER_FILES = {
    "s09": ROOT / "s09_jsonl_transcript" / "code.py",
    "s10": ROOT / "s10_workspace_memory" / "code.py",
    "s11": ROOT / "s11_user_memory" / "code.py",
    "s12": ROOT / "s12_cloud_memory" / "code.py",
    "s13": ROOT / "s13_output_externalization" / "code.py",
    "s14": ROOT / "s14_context_compact" / "code.py",
}


@dataclass(frozen=True)
class ChapterSet:
    """Loaded chapter modules, kept explicit so the walkthrough owns no core API."""

    s09: ModuleType
    s10: ModuleType
    s11: ModuleType
    s12: ModuleType
    s13: ModuleType
    s14: ModuleType


@dataclass(frozen=True)
class WalkthroughResult:
    """Inspectable output rather than an assertion-only integration test."""

    ok: bool
    checks: dict[str, bool]
    layers: dict[str, object]
    artifacts: dict[str, str]
    manifest_path: str


def _load_chapter(alias: str, path: Path) -> ModuleType:
    """Load a chapter file without copying its implementation into this example."""

    module_name = f"_learn_workbuddy_layered_memory_{alias}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load chapter module: {path}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses resolve their defining module through sys.modules while the
    # file executes, so registration must happen before exec_module().
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_chapters() -> ChapterSet:
    """Resolve the six existing chapter entrypoints used by the walkthrough."""

    modules = {name: _load_chapter(name, path) for name, path in CHAPTER_FILES.items()}
    return ChapterSet(**modules)


def _print_stage(number: int, title: str, detail: str) -> None:
    print(f"[{number}] {title}")
    print(f"    {detail}")


def _compact_under_teaching_pressure(
    s14: ModuleType,
    messages: list[dict],
    durable_state: object,
):
    """Force all layers with tiny limits, then restore the chapter constants.

    The production-shaped defaults need hundreds of kilobytes before compacting.
    A keyless walkthrough should prove the same control flow without allocating
    a huge fixture, so only this isolated module instance receives small limits.
    """

    original_limits = (
        s14.TOKEN_THRESHOLD,
        s14.MAX_TOOL_RESULT_TOKENS,
        s14.KEEP_RECENT_TURNS,
    )
    try:
        s14.TOKEN_THRESHOLD = 1
        s14.MAX_TOOL_RESULT_TOKENS = 8
        s14.KEEP_RECENT_TURNS = 6
        return s14.compact_context(
            messages,
            durable_state,
            summarizer=lambda _conversation: (
                "The migration is complete and no pending artifact review remains."
            ),
            verbose=False,
        )
    finally:
        (
            s14.TOKEN_THRESHOLD,
            s14.MAX_TOOL_RESULT_TOKENS,
            s14.KEEP_RECENT_TURNS,
        ) = original_limits


def run_walkthrough(home: Path) -> WalkthroughResult:
    """Run the layered memory story and validate every ownership boundary."""

    home = Path(home).expanduser().resolve()
    manifest_path = home / "layered_memory_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(
            f"walkthrough output already exists at {manifest_path}; choose a fresh --home"
        )
    home.mkdir(parents=True, exist_ok=True)
    chapters = load_chapters()
    recorded_at = datetime(2026, 8, 1, 12, tzinfo=timezone.utc)
    as_of = datetime(2026, 8, 14, 12, tzinfo=timezone.utc)

    # 1. Transcript is the append-only session evidence owner.  Selection names
    # one persisted event; it does not silently promote the entire conversation.
    transcript_path = home / "transcripts" / "memory-session.jsonl"
    transcript = chapters.s09.JSONLTranscript(transcript_path)
    transcript.append(
        {
            "type": "message",
            "role": "user",
            "content": "Keep workspace facts separate from user preferences.",
        }
    )
    transcript.append(
        {
            "type": "message",
            "role": "assistant",
            "content": "Use source-bearing layered memory and query-scoped recall.",
        }
    )
    persisted_events = [
        json.loads(line)
        for line in transcript_path.read_text(encoding="utf-8").splitlines()
    ]
    candidate = transcript.select_memory_candidate(
        persisted_events[1]["event_id"],
        summary="Layered memory keeps ownership and evidence boundaries explicit.",
        reason="The confirmed architecture decision is useful after this session.",
    )
    _print_stage(1, "Transcript evidence", candidate.source_id)

    # 2. Artifact owns the large body.  Later memory layers receive bounded
    # metadata, never a second copy of the raw tool output.
    artifact_session = home / "artifact-session"
    externalizer = chapters.s13.ToolResultExternalizer(artifact_session)
    large_output = "build verification log\n" + "verified module boundary\n" * 2_000
    externalized = externalizer.externalize(
        large_output,
        "bash",
        summary="Build verification completed for the layered memory walkthrough.",
    )
    artifact_memory = externalized.artifact.for_memory()
    retention_journal = chapters.s13.ArtifactRetentionJournal(artifact_session)
    artifact_claim = chapters.s13.ArtifactRetentionClaim.from_memory_reference(
        artifact_memory,
    )
    orphaned_artifact = externalizer.externalize(
        "temporary diagnostic output",
        "search",
        summary="Temporary diagnostic output with no durable owner.",
    ).artifact
    for artifact_path in (externalized.artifact.path, orphaned_artifact.path):
        os.utime(
            artifact_path,
            (recorded_at.timestamp(), recorded_at.timestamp()),
        )
    _print_stage(2, "Artifact reference", artifact_memory.source.source_id)

    # 3. Workspace memory keeps project facts in an append log, then distills
    # repeated evidence into one curated statement without deleting the log.
    workspace_dir = home / "workspace"
    workspace = chapters.s10.WorkspaceMemory(workspace_dir)
    decision = "Keep transcript, workspace, user, recall, and artifact ownership separate."
    first_fact = workspace.append_daily_log(
        decision,
        kind=chapters.s10.FactKind.DECISION,
        importance=3,
        source="transcript-selection",
        evidence={"source_id": candidate.source_id},
        recorded_at=recorded_at,
        fact_id="workspace-decision-1",
    )
    workspace.append_daily_log(
        decision,
        kind=chapters.s10.FactKind.DECISION,
        importance=3,
        source="review-confirmation",
        evidence={"source_id": f"{candidate.source_id}:review"},
        recorded_at=recorded_at,
        fact_id="workspace-decision-2",
    )
    lease_transaction, _ = retention_journal.publish_reference(
        artifact_claim,
        lambda: workspace.append_daily_log(
            artifact_memory.summary,
            kind=chapters.s10.FactKind.OUTCOME,
            importance=3,
            source="artifact",
            evidence={
                "source_id": artifact_memory.source.source_id,
                "artifact_path": artifact_memory.artifact_path,
                "content_sha256": artifact_memory.content_sha256,
            },
            recorded_at=recorded_at,
            fact_id="workspace-artifact-1",
        ),
        transaction_id="workspace-artifact-reference-1",
        prepared_at=recorded_at,
        committed_at=recorded_at,
    )
    distill = workspace.distill(
        policy=chapters.s10.DistillPolicy(
            minimum_age_days=0,
            minimum_importance=5,
            repeat_threshold=2,
        ),
        as_of=as_of,
    )
    _print_stage(
        3,
        "Workspace log and distill",
        f"{distill.eligible} evidence records -> {distill.created} curated entry",
    )

    # 4. User memory is keyed and user-scoped.  Repeating the same explicit
    # preference is a no-op; another user does not inherit it.
    # Both deliveries represent one event, even though the retry arrives later.
    user_root = home / "user-memory"
    alice = chapters.s11.UserMemory(user_root, user_id="alice")
    first_write = alice.set_preference(
        "response.style",
        "concise with source pointers",
        source="explicit-user-setting",
        updated_at="2026-08-14T12:00:00Z",
        source_event_id="walkthrough:preference-1",
    )
    repeated_write = alice.set_preference(
        "response.style",
        "concise with source pointers",
        source="explicit-user-setting",
        updated_at="2026-08-14T12:01:00Z",
        source_event_id="walkthrough:preference-1",
    )
    bob = chapters.s11.UserMemory(user_root, user_id="bob")
    user_isolated = bob.list_preferences() == []
    _print_stage(
        4,
        "User preference dedup and isolation",
        f"{first_write.status.value} -> {repeated_write.status.value}; bob empty={user_isolated}",
    )

    # 5. Remote history stores the selected transcript candidate.  Recall is a
    # query-scoped view with rank, score, and provenance; it never rewrites the
    # workspace or user stores above.
    remote_path = home / "remote-memory" / "alice.jsonl"
    remote = chapters.s12.RemoteMemoryStore(remote_path, user_id="alice")
    remote.append(
        kind=chapters.s12.MemoryKind.CONVERSATION,
        memory_id="remote-layered-memory-1",
        content=(
            "Layered memory separates workspace facts, user preferences, "
            "recalled history, transcript evidence, and artifacts."
        ),
        summary=candidate.summary,
        source=chapters.s12.MemorySource(**candidate.source_metadata()),
        stored_at=as_of,
    )
    recall = chapters.s12.RecallEngine(remote).recall(
        "layered memory ownership boundaries",
        query_id="walkthrough-query",
        as_of=as_of,
    )
    _print_stage(5, "Query-scoped recall", f"{len(recall.hits)} hit with source and score")

    # 6. Re-open every durable owner.  Compaction state is reconstructed from
    # recovered records; the compactor itself is deliberately not a database.
    restarted_transcript = chapters.s09.JSONLTranscript(transcript_path)
    recovered_session = restarted_transcript.recover()
    restarted_workspace = chapters.s10.WorkspaceMemory(workspace_dir)
    recovered_workspace = restarted_workspace.read_memory_md()
    restarted_alice = chapters.s11.UserMemory(user_root, user_id="alice")
    recovered_preferences = restarted_alice.list_preferences()
    restarted_remote = chapters.s12.RemoteMemoryStore(remote_path, user_id="alice")
    recovered_recall = chapters.s12.RecallEngine(restarted_remote).recall(
        "layered memory ownership boundaries",
        query_id="restart-query",
        as_of=as_of,
    )
    restarted_externalizer = chapters.s13.ToolResultExternalizer(artifact_session)
    restarted_journal = chapters.s13.ArtifactRetentionJournal(artifact_session)
    lease_recovery = restarted_journal.recover(now=as_of)
    cleanup_plan = restarted_externalizer.plan_cleanup_from_journal(
        restarted_journal,
        policy=chapters.s13.ArtifactCleanupPolicy(
            orphan_ttl_seconds=24 * 60 * 60,
            dry_run=False,
        ),
        now=as_of,
    )
    cleanup_report = restarted_externalizer.apply_cleanup_from_journal(
        cleanup_plan,
        restarted_journal,
        now=as_of,
    )
    recovered_artifact_head = restarted_externalizer.read_artifact(
        externalized.artifact,
        offset=0,
        limit=2,
    )
    _print_stage(
        6,
        "Crash-recovered artifact leases and cleanup",
        "lease recovered=1; referenced retained=1; expired orphan deleted=1",
    )

    durable_state = chapters.s14.DurableContextState(
        facts=(
            chapters.s14.DurableFact(
                fact_id=first_fact.fact_id,
                content=first_fact.content,
                source_pointer=candidate.source_id,
                last_confirmed_at=candidate.captured_at,
            ),
        ),
        pending_items=(
            chapters.s14.PendingItem(
                item_id="review-build-artifact",
                description="Review the externalized build evidence.",
                source_pointer=artifact_memory.source.source_id,
                last_confirmed_at=artifact_memory.source.captured_at,
            ),
        ),
    )
    messages = list(recovered_session["messages"])
    messages[1:1] = [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "walkthrough-tool-1",
                    "name": "read_file",
                    "input": {"path": "README.md"},
                }
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "walkthrough-tool-1",
                    "content": "large inline result " * 120,
                    "_read_path": "README.md",
                }
            ],
        },
    ]
    for index in range(8):
        messages.append(
            {
                "role": "assistant" if index % 2 == 0 else "user",
                "content": f"old turn {index}: " + "context detail " * 60,
            }
        )
    original_messages = copy.deepcopy(messages)
    compacted = _compact_under_teaching_pressure(
        chapters.s14,
        messages,
        durable_state,
    )
    # The fresh resolver receives trusted ownership roots, not paths supplied
    # by durable text. It locates both sources from their typed identifiers and
    # reports verification state without injecting source excerpts into Prompt.
    source_resolver = chapters.s14.SourcePointerResolver(
        transcript_root=home / "transcripts",
        artifact_root=home,
    )
    source_resolutions = chapters.s14.resolve_durable_sources(
        compacted.durable_state,
        source_resolver,
    )
    orphan_resolution = source_resolver.resolve(
        orphaned_artifact.source.source_id,
    )
    durable_context = chapters.s14.render_durable_context(
        compacted.durable_state,
        source_resolutions=source_resolutions,
    )
    poisoned_summary_visible = "migration is complete" in str(compacted.messages).lower()
    verified_source_count = sum(
        resolution.status is chapters.s14.SourceResolutionStatus.AVAILABLE
        for resolution in source_resolutions
    )
    durable_state_preserved = (
        compacted.durable_state is durable_state
        and first_fact.content in durable_context
        and artifact_memory.source.source_id in durable_context
        and "Review the externalized build evidence." in durable_context
        and messages == original_messages
    )
    _print_stage(
        7,
        "Compaction boundary",
        f"layers={','.join(compacted.applied_layers)}; "
        f"durable preserved={durable_state_preserved}; "
        f"sources verified={verified_source_count}",
    )

    curated_payload = json.loads(
        restarted_workspace.curated_file.read_text(encoding="utf-8")
    )
    checks = {
        "transcript_recovered": recovered_session["total_events"] == 2,
        "workspace_deduplicated": (
            distill.created == 1
            and len(curated_payload["entries"]) == 1
            and curated_payload["entries"][0]["occurrences"] == 2
        ),
        "user_preference_deduplicated": (
            first_write.status is chapters.s11.WriteStatus.CREATED
            and repeated_write.status is chapters.s11.WriteStatus.UNCHANGED
            and len(recovered_preferences) == 1
        ),
        "user_scope_isolated": user_isolated,
        "recall_recovered_with_source": (
            len(recovered_recall.hits) == 1
            and recovered_recall.hits[0].source.source_id == candidate.source_id
        ),
        "artifact_recovered_with_digest": (
            "build verification log" in recovered_artifact_head
            and len(artifact_memory.content_sha256) == 64
        ),
        "artifact_cleanup_preserved_references": (
            lease_recovery.claims == (artifact_claim,)
            and lease_recovery.pending_transaction_ids == ()
            and lease_recovery.states[0].transaction.transaction_id
            == lease_transaction.transaction_id
            and cleanup_report.counts == {
                "retained_referenced": 1,
                "deleted": 1,
            }
            and externalized.artifact.path.exists()
            and not orphaned_artifact.path.exists()
            and orphan_resolution.status
            is chapters.s14.SourceResolutionStatus.MISSING
        ),
        "compaction_exercised": bool(compacted.applied_layers),
        "adversarial_summary_exercised": poisoned_summary_visible,
        "durable_state_preserved": durable_state_preserved,
        "source_pointers_verified": verified_source_count == 2,
    }
    artifacts = {
        "transcript": str(transcript_path),
        "workspace_log": str(workspace.daily_log_path(recorded_at.date())),
        "workspace_curated": str(workspace.curated_file),
        "user_preferences": str(alice.preferences_path),
        "remote_memory": str(remote_path),
        "tool_result": artifact_memory.artifact_path,
        "retention_journal": str(retention_journal.path),
    }
    layers = {
        "transcript": {
            "events": recovered_session["total_events"],
            "selected_source_id": candidate.source_id,
        },
        "workspace": {
            "facts": len(restarted_workspace.read_all_facts()),
            "curated_entries": len(curated_payload["entries"]),
            "distill": asdict(distill),
        },
        "user": {
            "preference_count": len(recovered_preferences),
            "first_write": first_write.status.value,
            "repeated_write": repeated_write.status.value,
            "other_user_preference_count": len(bob.list_preferences()),
        },
        "recall": {
            "query_id": recovered_recall.query.query_id,
            "hits": [hit.to_dict() for hit in recovered_recall.hits],
        },
        "artifact": {
            "reference": artifact_memory.to_dict(),
            "lease_recovery": lease_recovery.to_dict(),
            "cleanup": cleanup_report.to_dict(),
            "orphan_resolution": orphan_resolution.to_dict(
                include_excerpt=False,
            ),
        },
        "compaction": {
            "applied_layers": list(compacted.applied_layers),
            "tokens_before": compacted.tokens_before,
            "tokens_after": compacted.tokens_after,
            "durable_context": durable_context,
            "source_resolutions": [
                resolution.to_dict(include_excerpt=False)
                for resolution in source_resolutions
            ],
        },
    }
    payload = {
        "ok": all(checks.values()),
        "checks": checks,
        "layers": layers,
        "artifacts": artifacts,
    }
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not payload["ok"]:
        failed = ", ".join(name for name, passed in checks.items() if not passed)
        raise RuntimeError(f"layered memory walkthrough failed: {failed}")
    return WalkthroughResult(
        ok=True,
        checks=checks,
        layers=layers,
        artifacts=artifacts,
        manifest_path=str(manifest_path),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Keyless layered memory walkthrough")
    parser.add_argument(
        "--home",
        help="fresh output directory (default: a temporary directory)",
    )
    args = parser.parse_args()
    home = Path(args.home) if args.home else Path(
        tempfile.mkdtemp(prefix="learn-workbuddy-layered-memory-")
    )
    print(f"Layered memory walkthrough — artifacts in {home.expanduser().resolve()}")
    result = run_walkthrough(home)
    print("RESULT: OK — layered memory boundaries survived compaction and restart.")
    print(f"Manifest: {result.manifest_path}")


if __name__ == "__main__":
    main()
