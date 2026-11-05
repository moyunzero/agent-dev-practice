"""可复用评估流水线：加载评测集 → 跑 RAG 模式 → 可选 RAGAs 打分。"""

from __future__ import annotations

import json
from pathlib import Path

from eval_common import run_ragas_eval
from rag_store import preview, run_pipeline, tag_chunk

EVAL_SET_PATH = Path(__file__).parent / "data" / "eval_set.json"
VALID_MODES = ("naive", "hybrid_rerank")


def load_eval_set(path: Path | None = None) -> list[dict]:
    p = path or EVAL_SET_PATH
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def collect_rows(
    mode: str,
    eval_set: list[dict],
    chunks,
    store,
    *,
    verbose: bool = True,
) -> list[dict]:
    if mode not in VALID_MODES:
        raise ValueError(f"mode 必须是 {VALID_MODES}，收到: {mode}")

    rows: list[dict] = []
    for item in eval_set:
        out = run_pipeline(mode, item["question"], chunks, store)
        rows.append(
            {
                "question": out["question"],
                "contexts": out["contexts"],
                "answer": out["answer"],
                "ground_truth": item.get("ground_truth", ""),
            }
        )
        if verbose:
            top1 = tag_chunk(out["contexts"][0])
            print(
                f"  [{mode}] {item['question'][:40]}\n"
                f"         Top-1=[{top1}] {preview(out['contexts'][0])}...\n"
                f"         answer: {preview(out['answer'], 72)}..."
            )
    if verbose:
        print()
    return rows


def score_mode(mode: str, rows: list[dict]) -> dict:
    print(f"=== RAGAs · {mode} ===\n")
    return run_ragas_eval(rows)


def compare_modes(
    modes: list[str],
    eval_set: list[dict],
    chunks,
    store,
    *,
    run_ragas: bool = True,
    verbose: bool = True,
) -> dict[str, dict]:
    """返回 {mode: {"rows": [...], "scores": {...}|None}}"""
    result: dict[str, dict] = {}
    for mode in modes:
        if verbose:
            print(f"--- 收集 · {mode} ---\n")
        rows = collect_rows(mode, eval_set, chunks, store, verbose=verbose)
        entry: dict = {"rows": rows, "scores": None}
        if run_ragas:
            entry["scores"] = score_mode(mode, rows)
        result[mode] = entry
    return result


def fmt_score(x: float) -> str:
    return f"{x:.4f}" if x == x else "nan"


def print_summary(results: dict[str, dict], modes: list[str]) -> None:
    if not all(results[m].get("scores") for m in modes):
        return
    print("=== 对比摘要 ===")
    for metric in ("faithfulness", "answer_relevancy"):
        parts = []
        for mode in modes:
            s = results[mode]["scores"][metric]
            parts.append(f"{mode}={fmt_score(s)}")
        print(f"  {metric:18s}  " + "  ".join(parts))
    print()
