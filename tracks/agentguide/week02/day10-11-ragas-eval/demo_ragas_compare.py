"""第 3 课：Naive RAG vs Hybrid+Rerank — 同一批问句，RAGAs 对比优化前后。"""

from __future__ import annotations

from eval_common import JUDGE_MODEL, run_ragas_eval
from rag_store import TOP_K, build_vectorstore, load_chunks, preview, run_pipeline, tag_chunk

EVAL_SET = [
    {
        "question": "chunk_overlap 是干什么的？",
        "ground_truth": "chunk_overlap 是相邻分块之间的重叠字符数，避免切断句子。",
    },
    {
        "question": "ERR_CHUNK_42 怎么处理？",
        "ground_truth": "停止写入，清空 collection，重新 embed 全量 chunk。",
    },
    {
        "question": "切文档时怎么让前后两段有一点重复，避免句子被切断？",
        "ground_truth": "调大 chunk_overlap，让相邻块有重叠字符。",
    },
]


def _fmt(x: float) -> str:
    return f"{x:.4f}" if x == x else "nan"


def _print_scores(label: str, scores: dict) -> None:
    f = scores["faithfulness"]
    a = scores["answer_relevancy"]
    extra = ""
    if scores.get("faithfulness_failed"):
        extra = f"  (faithfulness 失败 {scores['faithfulness_failed']} 条)"
    print(f"均值 faithfulness={_fmt(f)}  answer_relevancy={_fmt(a)}{extra}\n")


def collect_rows(mode: str, chunks, store) -> list[dict]:
    rows = []
    for item in EVAL_SET:
        out = run_pipeline(mode, item["question"], chunks, store)
        rows.append(
            {
                "question": out["question"],
                "contexts": out["contexts"],
                "answer": out["answer"],
                "ground_truth": item["ground_truth"],
            }
        )
        ctx_tag = "错误码" if any("ERR_CHUNK_42" in c for c in out["contexts"]) else "其它"
        top1 = tag_chunk(out["contexts"][0])
        print(
            f"  [{mode}] {item['question'][:36]}...\n"
            f"         Top-1=[{top1}] {preview(out['contexts'][0])}...\n"
            f"         (共 {len(out['contexts'])} 段；任一段含错误码={ctx_tag == '错误码'})"
        )
    print()
    return rows


def main() -> None:
    chunks = load_chunks()
    store = build_vectorstore(chunks)
    print(f"知识库 {len(chunks)} 条 chunk · TOP_K={TOP_K} · Judge: Ollama/{JUDGE_MODEL}")
    print("提示：库很小且 TOP_K=2 时，两档常会捞到多段，请看 Top-1 标签而不只看「任一段含错误码」。\n")

    print("=== 1) 跑两档流水线，收集 question / contexts / answer ===\n")
    naive_rows = collect_rows("naive", chunks, store)
    opt_rows = collect_rows("hybrid_rerank", chunks, store)

    print("=== 2) RAGAs 评测 Naive（仅向量）===\n")
    naive_scores = run_ragas_eval(naive_rows)
    _print_scores("Naive", naive_scores)

    print("=== 3) RAGAs 评测 Hybrid+Rerank ===\n")
    opt_scores = run_ragas_eval(opt_rows)
    _print_scores("Hybrid+Rerank", opt_scores)

    print("=== 4) 对比摘要 ===")
    for metric in ("faithfulness", "answer_relevancy"):
        n = naive_scores[metric]
        o = opt_scores[metric]
        if n != n or o != o:  # nan
            print(f"  {metric:18s}  naive={_fmt(n)}  hybrid+rerank={_fmt(o)}  (faithfulness 若 nan → Judge JSON 解析失败，见下文)")
            continue
        delta = o - n
        sign = "+" if delta >= 0 else ""
        print(f"  {metric:18s}  naive={n:.4f}  hybrid+rerank={o:.4f}  ({sign}{delta:.4f})")

    print(
        """
【本课要点】
1. 对比实验要固定：同一批问句、同一 Judge、同一生成 Prompt — 只改检索链。
2. ERR_CHUNK_42 问句上，hybrid+rerank 应更容易把错误码段送进 context → faithfulness 往往更高。
3. 口语问句（第 3 条）向量本来不差，优化链提升可能不明显 — 看分差不强求全涨。
4. faithfulness 依赖 Judge 输出严格 JSON；`qwen2:7b` 易失败 → 可 `OLLAMA_MODEL=qwen2.5-coder:7b` 重跑。

下节课：把评估收成可复用函数，换问句/换模式能再跑一轮。
"""
    )


if __name__ == "__main__":
    main()
