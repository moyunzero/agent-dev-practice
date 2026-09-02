"""建库用：按 batch_size 切片调用 embed_documents，避免一次塞爆内存/显存。"""

from __future__ import annotations

from langchain_huggingface import HuggingFaceEmbeddings


def embed_documents_chunked(
    emb: HuggingFaceEmbeddings,
    texts: list[str],
    batch_size: int = 32,
) -> list[list[float]]:
    """分批向量化。batch_size 从 32 起试；OOM 就减小。"""
    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i : i + batch_size]
        out.extend(emb.embed_documents(chunk))
    return out
