"""Answer-grounding example 的 evidence binding、引用完整性与 gold eval 契约。"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "examples" / "answer_grounding_eval" / "code.py"
FIXTURES = CODE.parent / "fixtures" / "cases.json"
RAG_CORPUS = ROOT / "examples" / "source_grounded_rag" / "fixtures" / "corpus"


@pytest.fixture(scope="module")
def grounding():
    name = "answer_grounding_eval_test_module"
    spec = importlib.util.spec_from_file_location(name, CODE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(name, None)


@pytest.fixture(scope="module")
def rag(grounding):
    return grounding._load_rag()


def _copy_corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    shutil.copytree(RAG_CORPUS, corpus)
    return corpus


def _index(rag, tmp_path: Path):
    index = rag.SourceIndex(
        _copy_corpus(tmp_path), tmp_path / "state" / "source-index.json"
    )
    index.sync()
    return index


def _case(grounding, case_id: str):
    return next(
        case for case in grounding.load_cases(FIXTURES) if case.case_id == case_id
    )


def _answer_for(grounding, rag, index, case_id: str):
    case = _case(grounding, case_id)
    search = rag.OfflineBM25Retriever(index).search(
        case.query,
        top_k=case.top_k,
        prompt_budget_chars=case.prompt_budget_chars,
    )
    evidence = grounding.EvidenceSet.from_search_result(search)
    answer = grounding.materialize_answer(case.answer, evidence)
    return case, search, evidence, answer


def test_fixture_evaluation_passes_public_answer_metrics(
    grounding, rag, tmp_path: Path
) -> None:
    report = grounding.evaluate(
        _index(rag, tmp_path), grounding.load_cases(FIXTURES), rag=rag
    )

    assert report.passed is True
    assert asdict(report.metrics) == {
        "verdict_accuracy": 1.0,
        "claim_citation_coverage": 1.0,
        "citation_validity_rate": 1.0,
        "gold_source_alignment": 1.0,
        "unsupported_claim_rate": 0.0,
        "negative_abstention_accuracy": 1.0,
        "adversarial_rejection_rate": 1.0,
        "deterministic_replay": 1.0,
    }
    assert len(report.cases) == 10
    assert all(case.expectation_met for case in report.cases)


def test_evidence_set_id_is_stable_but_query_bound(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    retriever = rag.OfflineBM25Retriever(index)
    first = retriever.search("permission hook approval", top_k=2)
    replay = retriever.search("permission hook approval", top_k=2)
    other = retriever.search("stale evidence citation", top_k=2)

    first_set = grounding.EvidenceSet.from_search_result(first)
    replay_set = grounding.EvidenceSet.from_search_result(replay)
    other_set = grounding.EvidenceSet.from_search_result(other)

    assert first_set.evidence_set_id == replay_set.evidence_set_id
    assert first_set.evidence_set_id != other_set.evidence_set_id
    assert first_set.records


def test_valid_answer_requires_selected_fresh_exact_quote(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    _case_data, _search, evidence, answer = _answer_for(
        grounding, rag, index, "valid-permission-answer"
    )

    report = grounding.AnswerVerifier(index, evidence).verify(answer)

    assert report.passed is True
    assert report.claim_count == 2
    assert report.cited_claims == 2
    assert report.valid_citations == report.citation_count == 2


def test_source_changed_after_answer_generation_fails_closed(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    _case_data, _search, evidence, answer = _answer_for(
        grounding, rag, index, "valid-stale-evidence-answer"
    )
    source = index.corpus_root / "rag-security.md"
    source.write_text(
        source.read_text(encoding="utf-8") + "\nchanged after answer generation\n",
        encoding="utf-8",
    )

    report = grounding.AnswerVerifier(index, evidence).verify(answer)

    assert report.passed is False
    assert "stale_evidence" in {issue.code for issue in report.issues}


def test_replayed_answer_is_rejected_even_when_citations_are_valid(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    _case_data, _search, evidence, answer = _answer_for(
        grounding, rag, index, "reject-replayed-evidence-set"
    )

    report = grounding.AnswerVerifier(index, evidence).verify(answer)

    assert report.passed is False
    assert report.valid_citations == 1
    assert {issue.code for issue in report.issues} == {"evidence_set_mismatch"}


def test_label_path_and_quote_must_resolve_to_the_same_selected_record(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    _case_data, _search, evidence, answer = _answer_for(
        grounding, rag, index, "valid-permission-answer"
    )
    claim = answer.claims[0]
    original = claim.citations[0]
    invalid = grounding.GroundedAnswer.from_dict(
        {
            "evidence_set_id": evidence.evidence_set_id,
            "claims": [
                {
                    "claim_id": claim.claim_id,
                    "text": claim.text,
                    "citations": [
                        {
                            "label": original.label,
                            "citation": "other.md#L1-L1",
                            "quote": original.quote,
                        }
                    ],
                }
            ],
            "abstained": False,
            "abstention_reason": None,
        }
    )

    report = grounding.AnswerVerifier(index, evidence).verify(invalid)

    assert report.passed is False
    assert {issue.code for issue in report.issues} == {
        "citation_metadata_mismatch"
    }


def test_exact_quote_preserves_internal_line_breaks(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    _case_data, _search, evidence, _answer = _answer_for(
        grounding, rag, index, "valid-permission-answer"
    )
    record = next(item for item in evidence.records if "\n" in item.text)
    quote = "\n".join(record.text.splitlines()[:3])
    answer = grounding.GroundedAnswer.from_dict(
        {
            "evidence_set_id": evidence.evidence_set_id,
            "claims": [
                {
                    "claim_id": "multiline-quote",
                    "text": "The selected evidence contains this exact multiline span.",
                    "citations": [
                        {
                            "label": record.label,
                            "citation": record.citation,
                            "quote": quote,
                        }
                    ],
                }
            ],
            "abstained": False,
            "abstention_reason": None,
        }
    )

    assert answer.claims[0].citations[0].quote == quote
    assert grounding.AnswerVerifier(index, evidence).verify(answer).passed is True


def test_runtime_integrity_does_not_pretend_to_be_semantic_entailment(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    case, _search, evidence, answer = _answer_for(
        grounding, rag, index, "reject-semantic-mismatch"
    )

    runtime = grounding.AnswerVerifier(index, evidence).verify(answer)
    gold = grounding.evaluate_gold_alignment(answer, case, evidence)

    assert runtime.passed is True
    assert gold.passed is False
    assert "unsupported_claim" in {issue.code for issue in gold.issues}


def test_abstention_is_explicit_and_cannot_carry_claims(
    grounding, rag, tmp_path: Path
) -> None:
    index = _index(rag, tmp_path)
    _case_data, _search, evidence, answer = _answer_for(
        grounding, rag, index, "valid-permission-answer"
    )
    contradictory = grounding.GroundedAnswer(
        evidence_set_id=evidence.evidence_set_id,
        claims=answer.claims,
        abstained=True,
        abstention_reason=None,
    )

    report = grounding.AnswerVerifier(index, evidence).verify(contradictory)

    assert report.passed is False
    assert {issue.code for issue in report.issues} == {
        "abstention_has_claims",
        "missing_abstention_reason",
    }


def test_fixture_schema_rejects_unknown_fields(grounding, tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    payload["cases"][0]["hidden_judge"] = True
    path = tmp_path / "invalid-cases.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(grounding.GroundingContractError, match="unknown fields"):
        grounding.load_cases(path)


def test_cli_is_keyless_and_writes_auditable_report(tmp_path: Path) -> None:
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
            "--cases",
            str(FIXTURES),
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
        (output / "answer-grounding-report.json").read_text(encoding="utf-8")
    )
    assert manifest["ok"] is True
    assert manifest["metrics"]["verdict_accuracy"] == 1
    assert manifest["metrics"]["unsupported_claim_rate"] == 0
    assert len(manifest["cases"]) == 10
    assert (output / "source-index.json").exists()
