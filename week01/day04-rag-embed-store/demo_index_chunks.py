"""第 3 课：把 Day3 的 chunk embed 后写入 Chroma 本地向量库。"""

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day04_demo"


def main() -> None:
    # --- Day3 复用：加载 + 切分 ---
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    )
    chunks = splitter.split_documents(docs)
    print(f"切分得到 {len(chunks)} 个 chunk\n")

    if PERSIST.exists():
        shutil.rmtree(PERSIST)
        print(f"已清空旧索引: {PERSIST}\n")

    # --- Day4：Embedding + 向量库 ---
    embeddings = HuggingFaceEmbeddings(model_name=MODEL)
    print(f"Embedding 模型: {MODEL}")
    print(f"持久化目录: {PERSIST}\n")

    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )

    count = vectorstore._collection.count()
    print(f"✅ 入库完成：collection `{COLLECTION}` 共 {count} 条")

    # 看一眼库里存了什么（向量本身是高维数组，这里只看关联的原文和 metadata）
    sample = vectorstore._collection.peek(limit=1)
    print("\n【库里一条记录长什么样】")
    print(f"  metadata: {sample['metadatas'][0]}")
    print(f"  正文预览: {sample['documents'][0][:80]}...")

    print(
        """

【本课要点】
1. Vector Store 存的不只是向量，还有 chunk 原文 + metadata（source 等）。
2. Chroma 把索引落到 chroma_db/ 目录，下次可复用，不用重新 embed。
3. 入库时每个 chunk 自动 embed 一次；下一课用问句做 similarity_search。
"""
    )


if __name__ == "__main__":
    main()
