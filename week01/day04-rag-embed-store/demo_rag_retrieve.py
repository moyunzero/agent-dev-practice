"""第 5 课：Day3 → Day4 全链路 — load → split → embed → store → search。"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day04_pipeline"


def build_index() -> Chroma:
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name=MODEL)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )


def retrieve(vectorstore: Chroma, query: str, k: int = 2) -> None:
    print(f"\n问句: {query}")
    print(f"Top-{k}:")
    for i, (doc, score) in enumerate(
        vectorstore.similarity_search_with_score(query, k=k), start=1
    ):
        preview = doc.page_content.replace("\n", " ")[:90]
        print(f"  [{i}] score={score:.4f} | {preview}...")


def main() -> None:
    print("=== RAG 检索链路（不含 LLM 生成）===\n")
    print("1. TextLoader 加载 MD")
    print("2. RecursiveCharacterTextSplitter 切分")
    print("3. HuggingFaceEmbeddings 向量化")
    print("4. Chroma 入库")
    print("5. similarity_search 检索 Top-K\n")

    vectorstore = build_index()
    print(f"索引就绪：{vectorstore._collection.count()} 条 chunk")

    retrieve(vectorstore, "FastAPI 路由怎么写？")
    retrieve(vectorstore, "chunk_overlap 是干什么的？")

    print(
        """

【本课要点】
完整 Naive RAG 检索半链路：
  文档 → Loader → Splitter → Embed → VectorStore → Query → Top-K chunks
Day5-6 会在 Top-K chunks 后面再接：塞进 Prompt → LLM 生成答案。
"""
    )


if __name__ == "__main__":
    main()
