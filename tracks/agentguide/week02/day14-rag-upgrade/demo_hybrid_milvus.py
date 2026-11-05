"""第 3 课：BM25 ∥ Milvus 向量 → RRF（Day9 Hybrid，向量库换成 Day12 Milvus）。"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient
from rank_bm25 import BM25Okapi

from milvus_config import COLLECTION, EMBED_MODEL, MILVUS_URI

DATA = Path(__file__).parent / "data" / "sample.md"
TOP_K = 3
RRF_K = 60
CANDIDATE_N = 5  # 每路召回条数，再融合


def load_chunks() -> list[str]:
    text = DATA.read_text(encoding="utf-8")
    return RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    ).split_text(text)


def tokenize(text: str) -> list[str]:
    """与 Day9 同款：英文词 + 中文按字（教学用）。"""
    text = text.lower()
    en = re.findall(r"[a-z0-9_]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    return en + zh


def bm25_ranked(chunks: list[str], query: str) -> list[tuple[str, float]]:
    bm25 = BM25Okapi([tokenize(c) for c in chunks])
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(chunks, scores, strict=True), key=lambda x: x[1], reverse=True)
    return [(c, float(s)) for c, s in ranked]


def milvus_vector_ranked(
    client: MilvusClient,
    model: HuggingFaceEmbeddings,
    query: str,
    n: int,
) -> list[tuple[str, float]]:
    q_vec = model.embed_query(query)
    hits = client.search(
        collection_name=COLLECTION,
        data=[q_vec],
        limit=n,
        output_fields=["text"],
    )[0]
    # COSINE distance：越小越相似；RRF 只用名次，不直接用分数
    return [(hit["entity"]["text"], float(hit["distance"])) for hit in hits]


def rrf_fuse(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (content, _raw) in enumerate(ranked, start=1):
            fused[content] = fused.get(content, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


def tag(text: str) -> str:
    # 重叠 chunk 可能同时含两节；优先标「错误码」主段落
    if "## 错误码" in text or text.strip().startswith("## 错误码"):
        return "错误码段"
    if "ERR_CHUNK_42" in text and "处理步骤" in text:
        return "错误码段"
    if "chunk_size" in text.lower() or "chunk_overlap" in text.lower() or "重叠" in text:
        return "分块参数段"
    return "其它"


def preview(text: str, n: int = 64) -> str:
    return text.replace("\n", " ")[:n]


def show(title: str, ranked: list[tuple[str, float]], label: str) -> None:
    print(title)
    for i, (content, score) in enumerate(ranked[:TOP_K], 1):
        print(f"  [{i}] {label}={score:.4f} [{tag(content)}] {preview(content)}...")
    print()


def main() -> None:
    client = MilvusClient(uri=MILVUS_URI)
    if not client.has_collection(COLLECTION):
        raise SystemExit("请先运行: uv run python demo_index_milvus.py")

    chunks = load_chunks()
    model = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    query = "ERR_CHUNK_42 怎么处理？"

    print("=== Day14 第 3 课：Hybrid（BM25 + Milvus）===\n")
    print(f"问句: {query}\n")

    bm25 = bm25_ranked(chunks, query)
    vector = milvus_vector_ranked(client, model, query, n=min(CANDIDATE_N, len(chunks)))
    hybrid = rrf_fuse([bm25[:CANDIDATE_N], vector])

    show("① 仅 BM25 Top-3（分越大越好）", bm25, "BM25")
    show("② 仅 Milvus 向量 Top-3（dist 越小越好）", vector, "dist")
    show("③ Hybrid RRF Top-3（融合分越大越好）", hybrid, "RRF")

    print(
        """
【本课要点】
1. 向量路：问句 embed → Milvus search（Day12）。
2. 关键词路：同一批 chunk 文本 → BM25（Day9）；不经过 Milvus。
3. RRF 按「名次」融合，不直接比 BM25 分和向量距离。
4. 下节课：Hybrid 候选 → CrossEncoder Rerank →（可选）生成。
"""
    )


if __name__ == "__main__":
    main()
