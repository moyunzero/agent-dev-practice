"""第 4 课：RAG 检索半链路 — 与 Day4 Chroma 流程对照，向量库换成 Milvus。"""

from __future__ import annotations

from pathlib import Path

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import DataType, MilvusClient

from milvus_config import DIM, MILVUS_URI

DATA = Path(__file__).parent / "data" / "sample.md"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day12_rag_pipeline"


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


def load_chunks() -> list[str]:
    text = DATA.read_text(encoding="utf-8")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    )
    return splitter.split_text(text)


def embed_texts(model: HuggingFaceEmbeddings, texts: list[str]) -> list[list[float]]:
    return model.embed_documents(texts)


def retrieve(
    client: MilvusClient,
    model: HuggingFaceEmbeddings,
    query: str,
    k: int = 5,
) -> None:
    q_vec = model.embed_query(query)
    hits = client.search(
        collection_name=COLLECTION,
        data=[q_vec],
        limit=k,
        output_fields=["text"],
    )[0]

    print(f"\n问句: {query}")
    print(f"Top-{k}:")
    for rank, hit in enumerate(hits, 1):
        preview = hit["entity"]["text"].replace("\n", " ")[:90]
        print(f"  [{rank}] id={hit['id']} distance={hit['distance']:.4f} | {preview}...")


def main() -> None:
    print("=== RAG 检索半链路（Milvus 版，不含 LLM 生成）===\n")
    print("Day4 Chroma 流程          →  Day12 Milvus 对照")
    print("TextLoader 读 MD          →  Path.read_text")
    print("RecursiveCharacterSplitter→  同款 splitter")
    print("HuggingFaceEmbeddings     →  同款 model (384 dim)")
    print("Chroma.from_documents     →  MilvusClient.insert + flush")
    print("similarity_search Top-K   →  client.search Top-K\n")

    client = MilvusClient(uri=MILVUS_URI)
    build_collection(client)

    chunks = load_chunks()
    model = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectors = embed_texts(model, chunks)
    assert len(vectors[0]) == DIM

    rows = [
        {"id": i + 1, "text": chunks[i], "embedding": vectors[i]}
        for i in range(len(chunks))
    ]
    client.insert(collection_name=COLLECTION, data=rows)
    client.flush(COLLECTION)
    print(f"索引就绪：{len(rows)} 条 chunk → {COLLECTION}")

    retrieve(client, model, "FastAPI 路由怎么写？")
    retrieve(client, model, "ERR_CHUNK_42 怎么处理？")

    print(
        """
【本课要点】
1. RAG 检索半链路不变：文档 → 切分 → embed → 向量库 → query embed → Top-K。
2. 换 Milvus 只改「存和搜」：Chroma 本地文件 → 独立服务 + pymilvus CRUD/search。
3. Top-K 的 text 可直接塞进 Day5 Prompt；后面 LLM 生成与向量库无关。
"""
    )


if __name__ == "__main__":
    main()
