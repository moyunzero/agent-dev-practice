"""第 4 课：可复用评估流水线 — 换模式 / 换问句快速再跑一轮。"""

from __future__ import annotations

import argparse

from eval_common import JUDGE_MODEL
from eval_pipeline import (
    VALID_MODES,
    collect_rows,
    compare_modes,
    load_eval_set,
    print_summary,
    score_mode,
)
from rag_store import TOP_K, build_vectorstore, load_chunks


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RAG 评估流水线（Day10 第 4 课）")
    p.add_argument(
        "--mode",
        choices=VALID_MODES,
        help="只跑一档：打印 Top-1 / answer（默认不跑 RAGAs，快）",
    )
    p.add_argument(
        "--compare",
        action="store_true",
        help="两档对比 + RAGAs（慢，同 demo_ragas_compare）",
    )
    p.add_argument(
        "--score",
        action="store_true",
        help="与 --mode 合用：对该档整份评测集跑 RAGAs",
    )
    p.add_argument(
        "--question",
        help="临时加一条问句（可配合 --mode，不写 eval_set.json）",
    )
    p.add_argument(
        "--ground-truth",
        default="",
        help="配合 --question 的标准答案（可选）",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    chunks = load_chunks()
    store = build_vectorstore(chunks)
    eval_set = load_eval_set()

    print(f"知识库 {len(chunks)} chunk · TOP_K={TOP_K} · Judge: Ollama/{JUDGE_MODEL}\n")

    if args.compare:
        results = compare_modes(
            list(VALID_MODES), eval_set, chunks, store, run_ragas=True
        )
        print_summary(results, list(VALID_MODES))
        print(
            """【本课要点】
1. eval_pipeline.py 把「收集 rows」和「RAGAs 打分」拆成可复用函数。
2. 评测集在 data/eval_set.json — 增删问句不用改 Python。
3. --mode 默认只收集（秒级）；--compare 才跑完整 Judge（十几分钟）。
4. 下节课：掌握检查 + 小改动（改 eval_set / 换 mode）。
"""
        )
        return

    if not args.mode:
        print("请指定 --mode naive|hybrid_rerank 或 --compare")
        print("示例:")
        print("  uv run python demo_eval_pipeline.py --mode hybrid_rerank --question 'ERR_CHUNK_42 怎么处理？'")
        print("  uv run python demo_eval_pipeline.py --compare")
        return

    if args.question:
        eval_set = [
            {"question": args.question, "ground_truth": args.ground_truth}
        ]

    rows = collect_rows(args.mode, eval_set, chunks, store)
    if args.score:
        scores = score_mode(args.mode, rows)
        print(
            f"faithfulness={scores['faithfulness']:.4f}  "
            f"answer_relevancy={scores['answer_relevancy']:.4f}"
        )
    else:
        print("（未跑 RAGAs；加 --score 对该档评测集打分，或 --compare 两档对比）")


if __name__ == "__main__":
    main()
