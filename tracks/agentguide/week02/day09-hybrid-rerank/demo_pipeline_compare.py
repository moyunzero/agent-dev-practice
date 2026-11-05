"""第 5 课：四档检索对比 — vector / bm25 / hybrid / hybrid+rerank。"""

from __future__ import annotations

from sentence_transformers import CrossEncoder

from demo_hybrid_rrf import bm25_ranked, preview, rrf_fuse, tag, vector_ranked
from demo_rerank import FINAL_K, RERANK_MODEL, rerank
from step01_keyword_vs_semantic import build_vectorstore, load_chunks

CANDIDATE_K = 5


def top_contents(ranked: list[tuple[str, float]], k: int) -> list[str]:
    return [c for c, _ in ranked[:k]]


def show_mode(name: str, texts: list[str]) -> None:
    print(f"=== {name} → 最终 Top-{len(texts)} ===")
    for i, text in enumerate(texts, 1):
        print(f"  [{i}] [{tag(text)}] {preview(text)}...")
    print()


def main() -> None:
    chunks = load_chunks()
    store = build_vectorstore(chunks)
    # 偏关键词：看 BM25 / Hybrid / Rerank 是否稳住错误码段
    query = "ERR_CHUNK_42 怎么处理？"
    print(f"问句: {query}\n")

    bm25 = bm25_ranked(chunks, query)
    vector = vector_ranked(store, query, n=len(chunks))
    hybrid = rrf_fuse([bm25, vector])

    show_mode("① 仅向量", top_contents(vector, FINAL_K))
    show_mode("② 仅 BM25", top_contents(bm25, FINAL_K))
    show_mode("③ Hybrid(RRF)", top_contents(hybrid, FINAL_K))

    candidates = top_contents(hybrid, CANDIDATE_K)
    ce = CrossEncoder(RERANK_MODEL)
    reranked = rerank(query, candidates, ce)
    show_mode("④ Hybrid + Rerank", top_contents(reranked, FINAL_K))

    print(
        """【本课要点】
对比四档时问自己：
- 仅向量：口语好不好？精确代号稳不稳？
- 仅 BM25：代号好不好？口语同义漏不漏？
- Hybrid：两路取长补短了吗？
- +Rerank：顺序有没有被「纠正」？值得多花一次精排成本吗？
掌握检查下一课。
"""
    )


if __name__ == "__main__":
    main()
