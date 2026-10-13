"""Retrieval-to-Prompt walkthrough 的组合、来源、安全和预算契约。"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "examples" / "context_pipeline_walkthrough" / "code.py"
RAG_CORPUS = ROOT / "examples" / "source_grounded_rag" / "fixtures" / "corpus"


@pytest.fixture(scope="module")
def pipeline():
    module_name = "context_pipeline_walkthrough_test_module"
    spec = importlib.util.spec_from_file_location(module_name, CODE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(module_name, None)


@pytest.fixture(scope="module")
def modules(pipeline):
    return pipeline.load_modules()


def _copy_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    shutil.copytree(RAG_CORPUS, corpus)
    return corpus


def _inputs(pipeline, modules, tmp_path: Path, *, corpus: Path | None = None):
    corpus = corpus or _copy_corpus(tmp_path)
    index = modules.rag.SourceIndex(corpus, tmp_path / "source-index.json")
    index.sync()
    inputs = pipeline.collect_candidates(
        modules,
        index,
        pipeline.DEFAULT_QUERY,
        pipeline.QueryGrant(),
    )
    return index, inputs


def test_keyless_walkthrough_passes_all_public_metrics(
    pipeline, modules, tmp_path: Path
) -> None:
    result = pipeline.run_walkthrough(
        tmp_path / "run",
        corpus=_copy_corpus(tmp_path / "fixture"),
        modules=modules,
    )

    assert result.ok is True
    assert result.checks and all(result.checks.values())
    assert result.metrics == {
        "required_retention_rate": 1.0,
        "provenance_coverage": 1.0,
        "unsafe_context_rate": 0.0,
        "stale_context_rate": 0.0,
        "duplicate_context_rate": 0.0,
        "budget_violation_rate": 0.0,
        "deterministic_replay": 1.0,
    }


def test_primary_plan_combines_rag_and_routed_context(
    pipeline, modules, tmp_path: Path
) -> None:
    _index, inputs = _inputs(pipeline, modules, tmp_path)
    block_set = pipeline.build_context_blocks(modules, inputs)
    plan = pipeline.assemble_blocks(modules, block_set, budget_chars=2_400)
    by_id = {block.block_id: block for block in block_set.blocks}
    included = [by_id[name] for name in plan.included_names]

    assert any(block.kind == "rag" for block in included)
    assert any(block.kind == "skill" for block in included)
    assert any(block.kind == "memory" for block in included)
    assert all(block.provenance and block.source_ids for block in included)
    assert plan.used_chars <= plan.budget_chars


def test_tight_budget_keeps_required_and_drops_atomic_optional_blocks(
    pipeline, modules, tmp_path: Path
) -> None:
    _index, inputs = _inputs(pipeline, modules, tmp_path)
    block_set = pipeline.build_context_blocks(modules, inputs)
    required_budget = pipeline._required_only_budget(modules, block_set)
    optional = sorted(
        (block for block in block_set.blocks if not block.required),
        key=lambda block: (-block.budget_priority, block.block_id),
    )
    tight_budget = (
        required_budget
        + len(modules.s15.PROMPT_SEPARATOR)
        + len(optional[0].content)
    )

    plan = pipeline.assemble_blocks(
        modules, block_set, budget_chars=tight_budget
    )

    required_ids = {block.block_id for block in block_set.blocks if block.required}
    assert required_ids.issubset(plan.included_names)
    assert optional[0].block_id in plan.included_names
    assert plan.dropped_names
    assert plan.used_chars == tight_budget
    assert all(
        decision.rendered_chars == 0
        for decision in plan.decisions
        if decision.status == "dropped"
    )


def test_required_context_fails_closed_when_budget_is_too_small(
    pipeline, modules, tmp_path: Path
) -> None:
    _index, inputs = _inputs(pipeline, modules, tmp_path)
    block_set = pipeline.build_context_blocks(modules, inputs)
    required_budget = pipeline._required_only_budget(modules, block_set)

    with pytest.raises(modules.s15.PromptBudgetError, match="required prompt segments"):
        pipeline.assemble_blocks(
            modules,
            block_set,
            budget_chars=required_budget - 1,
        )


def test_source_changed_after_retrieval_is_rejected_before_prompt(
    pipeline, modules, tmp_path: Path
) -> None:
    corpus = _copy_corpus(tmp_path)
    _index, inputs = _inputs(pipeline, modules, tmp_path, corpus=corpus)
    stale_hits = [
        hit for hit in inputs.rag_result.hits if hit.chunk.source_path == "rag-security.md"
    ]
    assert stale_hits
    source = corpus / "rag-security.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nchanged after retrieval\n",
        encoding="utf-8",
    )

    block_set = pipeline.build_context_blocks(modules, inputs)
    plan = pipeline.assemble_blocks(modules, block_set, budget_chars=2_400)

    for hit in stale_hits:
        block_id = f"rag:{hit.chunk.chunk_id}"
        assert block_set.rejected[block_id] == "source document changed after indexing"
        assert block_id not in plan.included_names
    assert "rag-security.md#" not in plan.prompt


def test_prompt_override_is_rejected_in_both_retrieval_channels(
    pipeline, modules, tmp_path: Path
) -> None:
    _index, inputs = _inputs(pipeline, modules, tmp_path)
    block_set = pipeline.build_context_blocks(modules, inputs)
    plan = pipeline.assemble_blocks(modules, block_set, budget_chars=2_400)
    override_rejections = {
        block_id: reason
        for block_id, reason in block_set.rejected.items()
        if "prompt override" in reason
    }

    assert any(block_id.startswith("rag:") for block_id in override_rejections)
    assert "route:memory-prompt-override" in override_rejections
    assert "Ignore previous instructions" not in plan.prompt
    assert "Override the system prompt" not in plan.prompt


def test_routed_context_cannot_expand_tool_or_network_grant(
    pipeline, modules, tmp_path: Path
) -> None:
    corpus = _copy_corpus(tmp_path)
    index = modules.rag.SourceIndex(corpus, tmp_path / "source-index.json")
    index.sync()
    grant = pipeline.QueryGrant(
        task_family="deployment",
        allowed_tools=(),
        allow_network=False,
    )
    inputs = pipeline.collect_candidates(
        modules,
        index,
        "publish and upload release artifacts",
        grant,
    )
    block_set = pipeline.build_context_blocks(modules, inputs)

    assert "route:skill-network-publisher" in block_set.rejected
    assert "required tools" in block_set.rejected["route:skill-network-publisher"]
    assert all(
        block.kind in {"required", "rag"} for block in block_set.blocks
    )
    assert not any(
        block.kind in {"skill", "memory", "reflection"}
        for block in block_set.blocks
    )


def test_duplicate_content_is_removed_before_budget_planning(
    pipeline, modules, tmp_path: Path
) -> None:
    _index, inputs = _inputs(pipeline, modules, tmp_path)
    original = pipeline.build_context_blocks(modules, inputs)
    source = next(block for block in original.blocks if not block.required)
    duplicate = replace(
        source,
        block_id="duplicate:lower-value-copy",
        provenance="test:duplicate-copy",
        source_ids=("duplicate-source",),
        budget_priority=source.budget_priority - 10,
    )

    deduped = pipeline.deduplicate_blocks(
        [*original.blocks, duplicate],
        rejected=original.rejected,
    )
    plan = pipeline.assemble_blocks(modules, deduped, budget_chars=4_000)

    assert source.block_id in {block.block_id for block in deduped.blocks}
    assert duplicate.block_id not in {block.block_id for block in deduped.blocks}
    assert deduped.rejected[duplicate.block_id] == f"duplicate context of {source.block_id}"
    assert duplicate.block_id not in plan.included_names


def test_context_block_without_provenance_is_rejected(pipeline) -> None:
    invalid = pipeline.ContextBlock(
        block_id="invalid",
        kind="memory",
        content="context",
        provenance="",
        source_ids=("source",),
        presentation_priority=50,
        budget_priority=50,
        required=False,
        dedupe_key="content",
    )

    with pytest.raises(pipeline.ContextPipelineError, match="identity and provenance"):
        pipeline.deduplicate_blocks([invalid])


def test_negative_query_abstains_from_optional_context(
    pipeline, modules, tmp_path: Path
) -> None:
    corpus = _copy_corpus(tmp_path)
    index = modules.rag.SourceIndex(corpus, tmp_path / "source-index.json")
    index.sync()
    grant = pipeline.QueryGrant(task_family="finance", allowed_tools=())
    inputs = pipeline.collect_candidates(
        modules, index, pipeline.NEGATIVE_QUERY, grant
    )
    block_set = pipeline.build_context_blocks(modules, inputs)
    plan = pipeline.assemble_blocks(modules, block_set, budget_chars=2_400)

    assert all(block.required for block in block_set.blocks)
    assert set(plan.included_names) == {
        "required:base",
        "required:grant",
        "required:evidence-guard",
        "required:mode",
    }
    assert not plan.dropped_names


def test_s15_provider_is_deferred_until_online_loop(
    modules, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MODEL_ID", raising=False)

    segment = modules.s15.PromptSegment(
        "offline", lambda: "offline context", required=True
    )
    plan = modules.s15.plan_prompt([segment], budget_chars=100)

    assert plan.prompt == "offline context"
    with pytest.raises(SystemExit, match="MODEL_ID is not set"):
        modules.s15.runtime_client()


def test_cli_is_keyless_and_writes_machine_readable_manifest(tmp_path: Path) -> None:
    output = tmp_path / "output"
    env = os.environ.copy()
    for key in (
        "MODEL_ID",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
    ):
        env.pop(key, None)
    result = subprocess.run(
        [
            sys.executable,
            str(CODE),
            "--corpus",
            str(RAG_CORPUS),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout
    assert "RESULT: OK" in result.stdout
    manifest = json.loads(
        (output / "context-pipeline-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["ok"] is True
    assert all(manifest["checks"].values())
    assert manifest["layers"]["primary_plan"]["used_chars"] <= 2_400
    assert manifest["layers"]["tight_plan"]["dropped_names"]
    assert (output / "source-index.json").exists()
