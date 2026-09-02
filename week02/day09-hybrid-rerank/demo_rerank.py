"""第 4 课：Rerank — 在 Hybrid 候选上用 CrossEncoder 精排（等价 Cohere Rerank 角色）。"""

from __future__ import annotations

from langchain_chroma import Chroma
from sentence_transformers import CrossEncoder

from demo_hybrid_rrf import bm25_ranked, preview, rrf_fuse, tag, vector_ranked
from step01_keyword_vs_semantic import build_vectorstore, load_chunks

CANDIDATE_K = 3  # 粗召回条数（融合后取前 N 条再 Rerank）
FINAL_K = 2      # 精排后塞进 Prompt 的条数
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


def rerank(query: str, candidates: list[str], model: CrossEncoder) -> list[tuple[str, float]]:
    pairs = [[query, text] for text in candidates]
    scores = model.predict(pairs)
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda x: x[1], reverse=True)
    return [(text, float(score)) for text, score in ranked]


def main() -> None:
    chunks = load_chunks()
    store: Chroma = build_vectorstore(chunks)
    query = "ERR_CHUNK_42 怎么处理？"

    print(f"问句: {query}")
    print(f"Rerank 模型: {RERANK_MODEL}\n")

    bm25 = bm25_ranked(chunks, query)
    vector = vector_ranked(store, query, n=len(chunks))
    fused = rrf_fuse([bm25, vector])[:CANDIDATE_K]

    print(f"=== Hybrid RRF 粗召回 Top-{CANDIDATE_K} ===")
    for i, (content, score) in enumerate(fused, 1):
        print(f"  [{i}] RRF={score:.4f} [{tag(content)}] {preview(content)}...")
    print()

    candidates = [content for content, _ in fused]
    ce = CrossEncoder(RERANK_MODEL)
    reranked = rerank(query, candidates, ce)

    print(f"=== CrossEncoder 精排后 Top-{FINAL_K} ===")
    for i, (content, score) in enumerate(reranked[:FINAL_K], 1):
        print(f"  [{i}] rerank={score:.4f} [{tag(content)}] {preview(content)}...")
    print()

    print(
        """【本课要点】
1. 召回（Hybrid/RRF）：先「宽」地捞候选，允许噪声。
2. Rerank：对 (问句, chunk) 逐对打分，重新排序 — 比单向量相似度更准。
3. Cohere Rerank 与本课 CrossEncoder 在流水线里是同一角色：精排模型（本课用本地免 Key）。
4. 候选太少 → 精排没东西可选；候选太多 → 慢。CANDIDATE_K 是工程权衡。
"""
    )


if __name__ == "__main__":
    main()
