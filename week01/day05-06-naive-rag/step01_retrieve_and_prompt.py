"""第 1 课：检索结果如何塞进 Prompt（今天还不调 LLM）。"""

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 2


def build_vectorstore() -> Chroma:
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)

    if PERSIST.exists():
        shutil.rmtree(PERSIST)

    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name="naive_rag",
    )


def format_context(chunks) -> str:
    return "\n\n---\n\n".join(doc.page_content for doc in chunks)


def build_rag_prompt(question: str, context: str) -> str:
    return f"""请仅根据以下资料回答问题。资料中没有的信息请说「资料未提及」。

【资料】
{context}

【问题】
{question}
"""


def main() -> None:
    print("=== Naive RAG 第 1 课：检索 → 拼 Prompt（不调 LLM）===\n")

    store = build_vectorstore()
    print(f"索引就绪：{store._collection.count()} 条 chunk\n")

    question = "chunk_overlap 是干什么的？"
    retrieved = store.similarity_search(question, k=TOP_K)

    print(f"问句: {question}")
    print(f"检索 Top-{TOP_K}，得到 {len(retrieved)} 段资料\n")

    for i, doc in enumerate(retrieved, start=1):
        preview = doc.page_content.replace("\n", " ")[:80]
        print(f"  [chunk {i}] {preview}...")

    context = format_context(retrieved)
    prompt = build_rag_prompt(question, context)

    print("\n=== 下面这段就是 Day5 要交给 LLM 的 Prompt ===\n")
    print(prompt)

    print(
        """

【本课要点】
Day4 结束在 Top-K chunk；Day5 新的一步是「把 chunk 拼进 Prompt」。
完整 Naive RAG：
  ① 检索（Day3/4）→ ② 拼 Prompt（本课）→ ③ LCEL 调模型（下节课）→ ④ FastAPI 暴露（再下节）
"""
    )


if __name__ == "__main__":
    main()
