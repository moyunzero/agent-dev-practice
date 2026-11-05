"""升级 RAG 检索+可选生成（供 FastAPI /ask 复用）。"""

from __future__ import annotations

import json
import os
import urllib.request

from langchain_huggingface import HuggingFaceEmbeddings
from pymilvus import MilvusClient
from sentence_transformers import CrossEncoder

from demo_hybrid_milvus import (
    bm25_ranked,
    load_chunks,
    milvus_vector_ranked,
    rrf_fuse,
)
from milvus_config import COLLECTION, EMBED_MODEL, MILVUS_URI

CANDIDATE_K = 4
FINAL_K = 1
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def retrieve_upgraded(question: str) -> list[str]:
    client = MilvusClient(uri=MILVUS_URI)
    if not client.has_collection(COLLECTION):
        raise RuntimeError("Milvus 无 collection，请先: uv run python demo_index_milvus.py")
    chunks = load_chunks()
    emb = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vector = milvus_vector_ranked(client, emb, question, n=len(chunks))
    bm25 = bm25_ranked(chunks, question)
    hybrid = rrf_fuse([bm25, vector])
    candidates = [c for c, _ in hybrid[:CANDIDATE_K]]
    ce = CrossEncoder(RERANK_MODEL)
    pairs = [[question, text] for text in candidates]
    scores = ce.predict(pairs)
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda x: x[1], reverse=True)
    return [c for c, _ in ranked[:FINAL_K]]


def generate_answer(question: str, contexts: list[str]) -> str:
    ctx = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
    prompt = (
        "只根据下列上下文回答问题；上下文没有的信息就说不知道。\n\n"
        f"上下文:\n{ctx}\n\n问题: {question}\n答案:"
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


def ask(question: str, *, generate: bool = True) -> dict:
    sources = retrieve_upgraded(question)
    answer = generate_answer(question, sources) if generate else "(retrieve-only)"
    return {
        "question": question,
        "answer": answer,
        "model": OLLAMA_MODEL if generate else "none",
        "pipeline": "milvus+bm25/rrf+rerank",
        "sources": [{"preview": s[:200]} for s in sources],
    }
