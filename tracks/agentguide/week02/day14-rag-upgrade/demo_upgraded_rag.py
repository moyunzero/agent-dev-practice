"""第 4 课：升级 RAG — Hybrid → Rerank；对照仅向量（Naive）。可选 Ollama 生成。"""

from __future__ import annotations

import os
import urllib.request

from langchain_huggingface import HuggingFaceEmbeddings
from pymilvus import MilvusClient
from sentence_transformers import CrossEncoder

from demo_hybrid_milvus import (
    TOP_K,
    bm25_ranked,
    load_chunks,
    milvus_vector_ranked,
    preview,
    rrf_fuse,
    tag,
)
from milvus_config import COLLECTION, EMBED_MODEL, MILVUS_URI

CANDIDATE_K = 4
FINAL_K = 1
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def rerank(query: str, candidates: list[str], model: CrossEncoder) -> list[tuple[str, float]]:
    pairs = [[query, text] for text in candidates]
    scores = model.predict(pairs)
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda x: x[1], reverse=True)
    return [(text, float(score)) for text, score in ranked]


def show_mode(name: str, texts: list[str]) -> None:
    print(f"=== {name} → Top-{len(texts)} ===")
    for i, text in enumerate(texts, 1):
        print(f"  [{i}] [{tag(text)}] {preview(text, 72)}...")
    print()


def ollama_available() -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def generate_answer(query: str, contexts: list[str]) -> str:
    import json

    ctx = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
    prompt = (
        "只根据下列上下文回答问题；上下文没有的信息就说不知道。\n\n"
        f"上下文:\n{ctx}\n\n问题: {query}\n答案:"
    )
    body = json.dumps(
        {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        ensure_ascii=False,
    ).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return str(data.get("response", "")).strip()


def main() -> None:
    client = MilvusClient(uri=MILVUS_URI)
    if not client.has_collection(COLLECTION):
        raise SystemExit("请先运行: uv run python demo_index_milvus.py")

    chunks = load_chunks()
    emb = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    query = "ERR_CHUNK_42 怎么处理？"

    print("=== Day14 第 4 课：Naive vs Upgraded ===\n")
    print(f"问句: {query}")
    print(f"Rerank: {RERANK_MODEL}\n")

    # ① Naive：仅 Milvus 向量
    vector = milvus_vector_ranked(client, emb, query, n=len(chunks))
    naive_top = [c for c, _ in vector[:FINAL_K]]
    show_mode("① Naive（仅 Milvus 向量）", naive_top)

    # ② Hybrid RRF
    bm25 = bm25_ranked(chunks, query)
    hybrid = rrf_fuse([bm25, vector])
    hybrid_top = [c for c, _ in hybrid[:FINAL_K]]
    show_mode("② Hybrid RRF（无 Rerank）", hybrid_top)

    # ③ Hybrid + Rerank
    candidates = [c for c, _ in hybrid[:CANDIDATE_K]]
    ce = CrossEncoder(RERANK_MODEL)
    reranked = rerank(query, candidates, ce)
    upgraded_top = [c for c, _ in reranked[:FINAL_K]]
    show_mode("③ Upgraded（Hybrid + Rerank）", upgraded_top)

    print("对照：看错误码段是否进 Top-1 / Top-2；③ 是否比 ① 更稳。\n")

    if ollama_available():
        print(f"=== 可选生成（Ollama {OLLAMA_MODEL}）===")
        print("用 ③ 的 contexts 生成：\n")
        print(generate_answer(query, upgraded_top))
        print()
    else:
        print("（未检测到 Ollama，跳过生成；检索升级已完成。）\n")

    print(
        """
【本课要点】
1. 升级 = Milvus 向量库 + BM25/RRF 混合 + Rerank（上游三件套）。
2. RRF 用名次融合；Rerank 对 (query, chunk) 打相关性分再排序。
3. 生成仍是 Prompt + LLM；换的是塞进 Prompt 的 contexts 质量。
"""
    )


if __name__ == "__main__":
    main()
