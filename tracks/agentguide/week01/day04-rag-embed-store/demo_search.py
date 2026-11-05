"""第 4 课：从 Chroma 做 Top-K 相似度检索。"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

PERSIST = Path(__file__).parent / "chroma_db"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day04_demo"


def main() -> None:
    embeddings = HuggingFaceEmbeddings(model_name=MODEL)
    vectorstore = Chroma(
        persist_directory=str(PERSIST),
        embedding_function=embeddings,
        collection_name=COLLECTION,
    )

    total = vectorstore._collection.count()
    print(f"当前 collection 共 {total} 条\n")

    query = "FastAPI 路由怎么写？"
    k = 1
    print(f"问句: {query}")
    print(f"Top-{k} 检索结果:\n")

    results = vectorstore.similarity_search_with_score(query, k=k)
    for i, (doc, score) in enumerate(results, start=1):
        preview = doc.page_content.replace("\n", " ")[:100]
        print(f"[{i}] score={score:.4f}")
        print(f"    metadata: {doc.metadata}")
        print(f"    正文: {preview}...\n")

    print(
        """【本课要点】
1. similarity_search_with_score：问句 embed 后与库中向量比距离，取 Top-K。
2. score 越小通常表示越相似（Chroma 默认返回 cosine 距离，即 1 - 余弦相似度；不是 L2，除非建库时改过度量）。
3. 返回的 Document 带 page_content + metadata，可直接用于 RAG Prompt。
"""
    )


if __name__ == "__main__":
    main()
