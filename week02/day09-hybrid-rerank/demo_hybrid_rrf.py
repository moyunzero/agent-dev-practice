"""第 3 课：Hybrid Search — BM25 + 向量双路召回，RRF 融合排序。"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from step01_keyword_vs_semantic import build_vectorstore, load_chunks, tokenize

TOP_K = 3
RRF_K = 60  # 常见默认常数，越大越「平滑」


def bm25_ranked(chunks, query: str) -> list[tuple[str, float]]:
    corpus_tokens = [tokenize(c.page_content) for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(
        zip(chunks, scores, strict=True),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(doc.page_content, float(score)) for doc, score in ranked]


def vector_ranked(store: Chroma, query: str, n: int) -> list[tuple[str, float]]:
    hits = store.similarity_search_with_score(query, k=n)
    hits.sort(key=lambda x: x[1])
    return [(doc.page_content, float(score)) for doc, score in hits]


def rrf_fuse(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """按 chunk 正文去重；融合分 = Σ 1/(k + rank)。"""
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (content, _raw) in enumerate(ranked, start=1):
            fused[content] = fused.get(content, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


def preview(text: str, n: int = 72) -> str:
    return text.replace("\n", " ")[:n]


def tag(text: str) -> str:
    if "ERR_CHUNK_42" in text:
        return "错误码段"
    if "chunk_overlap" in text.lower() or "重叠" in text:
        return "分块参数段"
    return "其它"


def show_list(title: str, ranked: list[tuple[str, float]], score_label: str) -> None:
    print(title)
    for i, (content, score) in enumerate(ranked[:TOP_K], 1):
        print(f"  [{i}] {score_label}={score:.4f} [{tag(content)}] {preview(content)}...")
    print()


def main() -> None:
    chunks = load_chunks()
    store = build_vectorstore(chunks)
    query = "ERR_CHUNK_42 怎么处理？"

    print(f"问句: {query}\n")

    bm25 = bm25_ranked(chunks, query)
    vector = vector_ranked(store, query, n=len(chunks))
    hybrid = rrf_fuse([bm25, vector])

    show_list("=== BM25 Top-3（分数越大越好）===", bm25, "BM25")
    show_list("=== 向量 Top-3（距离越小越好）===", vector, "dist")
    show_list("=== RRF 融合 Top-3（RRF 分越大越好）===", hybrid, "RRF")

    print(
        """【本课要点】
1. Hybrid = 两路各自排序 → RRF 只看「排名」，不看原始分数尺度。
2. 某段在两路都排得靠前 → RRF 分叠加更高。
3. 口语问句可再跑一遍对比：向量路可能抬分块参数段，BM25 路可能偏弱 — 融合能取长补短。
下节课：Rerank 在融合候选上做精排。
"""
    )


if __name__ == "__main__":
    main()
