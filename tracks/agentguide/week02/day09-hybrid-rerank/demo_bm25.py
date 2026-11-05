"""第 2 课：手撕 BM25 — 关键词检索 Top-K，并看分数从哪来。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from step01_keyword_vs_semantic import tokenize

DATA = Path(__file__).parent / "data" / "sample.md"
TOP_K = 3


def load_chunks():
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    return RecursiveCharacterTextSplitter(
        chunk_size=220, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)


def bm25_search(chunks, query: str, k: int = TOP_K):
    corpus_tokens = [tokenize(c.page_content) for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    q_tokens = tokenize(query)
    scores = bm25.get_scores(q_tokens)
    ranked = sorted(
        zip(chunks, scores, strict=True),
        key=lambda x: x[1],
        reverse=True,  # BM25：分数越大越相关
    )
    return q_tokens, ranked[:k]


def main() -> None:
    chunks = load_chunks()
    print(f"知识库共 {len(chunks)} 条 chunk\n")

    queries = [
        "ERR_CHUNK_42 怎么处理？",
        "chunk_overlap 是干什么的？",
        "切文档时怎么让前后两段有一点重复？",  # 几乎对不上文档原词 → BM25 往往较弱
    ]

    for query in queries:
        q_tokens, ranked = bm25_search(chunks, query)
        print(f"=== 问句: {query}")
        print(f"分词后: {q_tokens}")
        for i, (doc, score) in enumerate(ranked, 1):
            preview = doc.page_content.replace("\n", " ")[:80]
            print(f"  [{i}] BM25={score:.4f} | {preview}...")
        print()

    print(
        """【本课要点】
1. BM25 分数：越大越相关（注意：和 Chroma 的「距离越小越好」相反）。
2. 先分词，再按词在文档里的出现情况打分；不懂同义词。
3. 口语问法若几乎不含文档原词，BM25 Top-1 可能偏弱 — 这就是要混合向量的原因。
下节课：BM25 + 向量 + RRF 融合。
"""
    )


if __name__ == "__main__":
    main()
