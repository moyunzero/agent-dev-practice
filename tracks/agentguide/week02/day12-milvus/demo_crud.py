"""第 3 课：insert / search / delete — Milvus CRUD + 向量 Top-K。"""

from __future__ import annotations

from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient

from milvus_config import COLLECTION, DIM, MILVUS_URI

DATA = Path(__file__).parent / "data" / "sample.md"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def load_chunks() -> list[str]:
    text = DATA.read_text(encoding="utf-8")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=220, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    )
    return splitter.split_text(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return model.embed_documents(texts)


def main() -> None:
    client = MilvusClient(uri=MILVUS_URI)
    if not client.has_collection(COLLECTION):
        raise SystemExit(f"请先运行 demo_create_collection.py 创建 {COLLECTION}")

    chunks = load_chunks()
    vectors = embed_texts(chunks)
    assert len(vectors[0]) == DIM, f"向量 dim 应为 {DIM}"

    # --- Insert：手动 id + embedding（与 create_collection auto_id=False 对应）
    rows = [{"id": i + 1, "embedding": vectors[i]} for i in range(len(chunks))]
    client.insert(collection_name=COLLECTION, data=rows)
    client.flush(COLLECTION)
    print(f"Insert {len(rows)} 条 → {COLLECTION}\n")

    for i, chunk in enumerate(chunks, 1):
        preview = chunk.replace("\n", " ")[:60]
        print(f"  id={i} | {preview}...")

    # --- Search：问句 embed → Top-2
    query = "ERR_CHUNK_42 怎么处理？"
    q_vec = embed_texts([query])[0]
    hits = client.search(
        collection_name=COLLECTION,
        data=[q_vec],
        limit=2,
        output_fields=["id"],
    )[0]

    print(f"\n问句: {query}")
    print("Search Top-2:")
    for rank, hit in enumerate(hits, 1):
        doc_id = hit["id"]
        dist = hit["distance"]
        preview = chunks[doc_id - 1].replace("\n", " ")[:60]
        print(f"  [{rank}] id={doc_id} distance={dist:.4f} | {preview}...")

    # --- Delete：删掉 id=1 再搜一次
    client.delete(collection_name=COLLECTION, ids=[1])
    client.flush(COLLECTION)
    count = client.query(collection_name=COLLECTION, filter="id >= 0", output_fields=["id"])
    print(f"\nDelete id=1 后剩余 {len(count)} 条")

    hits2 = client.search(collection_name=COLLECTION, data=[q_vec], limit=2, output_fields=["id"])[0]
    print("再次 Search Top-2:")
    for rank, hit in enumerate(hits2, 1):
        print(f"  [{rank}] id={hit['id']} distance={hit['distance']:.4f}")

    print(
        """
【本课要点】
1. insert 的 embedding 列 dim 必须 = 建表时的 384。
2. search 传入 query 向量，返回 Top-K + distance（COSINE 下越小越相似）。
3. delete 按 id 删；flush 后检索才稳定看到最新数据。
下节课：与 Day4 RAG 检索流程对照串联。
"""
    )


if __name__ == "__main__":
    main()
