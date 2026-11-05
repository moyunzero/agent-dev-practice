"""Day26 Lesson 2 — Embedding：逐条 embed_query vs 一批 embed_documents。"""

from __future__ import annotations

import os
import time

from langchain_huggingface import HuggingFaceEmbeddings

# 小模型、本地可下；首次会下载
MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
N = int(os.getenv("N_DOCS", "32"))

texts = [f"RAG batching demo sentence number {i}." for i in range(N)]


def main() -> None:
    emb = HuggingFaceEmbeddings(model_name=MODEL)
    # 暖机，避免把首次加载算进对比
    _ = emb.embed_query("warmup")

    t0 = time.perf_counter()
    one = [emb.embed_query(t) for t in texts]
    t_one = time.perf_counter() - t0

    t0 = time.perf_counter()
    batch = emb.embed_documents(texts)
    t_batch = time.perf_counter() - t0

    assert len(one) == len(batch) == N
    assert len(one[0]) == len(batch[0])
    print(f"model={MODEL}  docs={N}  dim={len(batch[0])}")
    print(f"逐条 embed_query ×{N}: {t_one:.2f}s  ({N / t_one:.1f} docs/s)")
    print(f"一批 embed_documents : {t_batch:.2f}s  ({N / t_batch:.1f} docs/s)")
    if t_batch > 0:
        print(f"批处理更快约: {t_one / t_batch:.1f}x")


if __name__ == "__main__":
    main()
