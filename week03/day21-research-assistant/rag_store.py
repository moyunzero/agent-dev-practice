"""本地知识库：加载 data/nebula_notes.md → Chroma → similarity_search。"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "nebula_notes.md"
PERSIST = ROOT / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day21_nebula"
TOP_K = 2


def get_vectorstore(*, rebuild: bool = False) -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if rebuild and PERSIST.exists():
        import shutil

        shutil.rmtree(PERSIST)

    if PERSIST.exists() and not rebuild:
        return Chroma(
            persist_directory=str(PERSIST),
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )

    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=280,
        chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    ).split_documents(docs)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )


def search_kb(query: str, *, k: int = TOP_K) -> str:
    store = get_vectorstore()
    hits = store.similarity_search(query, k=k)
    if not hits:
        return "知识库无命中。"
    parts = []
    for i, d in enumerate(hits, 1):
        parts.append(f"[{i}] {d.page_content.strip()}")
    return "\n\n".join(parts)
