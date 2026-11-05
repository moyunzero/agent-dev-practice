"""第 2 课：chunk → embed → Milvus（带 text 字段，供后续 Hybrid 取回正文）。"""

from __future__ import annotations

from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import DataType, MilvusClient

from milvus_config import COLLECTION, DIM, EMBED_MODEL, MILVUS_URI

DATA = Path(__file__).parent / "data" / "sample.md"


def load_chunks() -> list[str]:
    text = DATA.read_text(encoding="utf-8")
    return RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    ).split_text(text)


def build_collection(client: MilvusClient) -> None:
    if client.has_collection(COLLECTION):
        client.drop_collection(COLLECTION)

    schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
    schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
    schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4096)
    schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=DIM)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        index_type="AUTOINDEX",
        metric_type="COSINE",
    )
    client.create_collection(
        collection_name=COLLECTION,
        schema=schema,
        index_params=index_params,
    )


def main() -> None:
    print("=== Day14 第 2 课：索引入 Milvus ===\n")
    print(f"URI: {MILVUS_URI}")
    print(f"Collection: {COLLECTION} (dim={DIM})\n")

    client = MilvusClient(uri=MILVUS_URI)
    build_collection(client)

    chunks = load_chunks()
    model = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectors = model.embed_documents(chunks)
    assert len(vectors[0]) == DIM

    rows = [
        {"id": i + 1, "text": chunks[i], "embedding": vectors[i]}
        for i in range(len(chunks))
    ]
    client.insert(collection_name=COLLECTION, data=rows)
    client.flush(COLLECTION)

    print(f"已写入 {len(rows)} 条 chunk\n")
    for r in rows:
        preview = r["text"].replace("\n", " ")[:70]
        print(f"  id={r['id']} | {preview}...")

    # 冒烟：向量 Top-2
    q = "ERR_CHUNK_42 怎么处理？"
    q_vec = model.embed_query(q)
    hits = client.search(
        collection_name=COLLECTION,
        data=[q_vec],
        limit=2,
        output_fields=["text"],
    )[0]
    print(f"\n冒烟 Search · 问句: {q}")
    for i, hit in enumerate(hits, 1):
        preview = hit["entity"]["text"].replace("\n", " ")[:70]
        print(f"  [{i}] id={hit['id']} dist={hit['distance']:.4f} | {preview}...")

    print(
        """
【本课要点】
1. 与 Day12 相同：schema 必须带 text，否则 Hybrid/Rerank 拿不到正文。
2. BM25 仍要对「同一批 chunk 文本」在内存建词袋索引——Milvus 不管关键词打分。
3. 下节课：BM25 ∥ Milvus 向量 → RRF。
"""
    )


if __name__ == "__main__":
    main()
