"""第 1 课：问句—文档表述鸿沟 — 同一意图，不同问法，检索 Top-1 可能不同。"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day08_demo"


def build_vectorstore() -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if PERSIST.exists():
        return Chroma(
            persist_directory=str(PERSIST),
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )

    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )


def show_top1(store: Chroma, label: str, query: str) -> None:
    doc, score = store.similarity_search_with_score(query, k=1)[0]
    preview = doc.page_content.replace("\n", " ")[:90]
    hit = "chunk_overlap" in doc.page_content.lower() or "重叠" in doc.page_content
    print(f"【{label}】")
    print(f"  问句: {query}")
    print(f"  Top-1 score={score:.4f}  命中分块参数段={'是' if hit else '否'}")
    print(f"  预览: {preview}...\n")


def main() -> None:
    store = build_vectorstore()
    print(f"索引就绪，共 {store._collection.count()} 条 chunk\n")

    show_top1(store, "问法 A · 贴近文档术语", "chunk_overlap 是干什么的？")
    show_top1(store, "问法 B · 口语描述同一意图", "切文档时怎么让前后两段有一点重复，避免句子被切断？")

    print(
        """【本课要点】
1. 检索质量不只取决于索引，还取决于「拿什么去问」。
2. 用户问法与文档表述不一致时，Top-1 可能偏了 — 这就是 Query Transformation 要解决的问题。
3. 改写发生在检索之前：先变换问句，再 similarity_search。
下节课：Multi-Query — 让 LLM 从一个问句生成多条检索 query。
"""
    )


if __name__ == "__main__":
    main()
