"""Day3 第 1 课：加载 MD + Text Splitter 分块。"""

from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path(__file__).parent / "data" / "sample.md"


def main() -> None:
    # --- Loader：把文件读成 Document 列表 ---
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    print(f"加载完成：{len(docs)} 个 Document")
    print(f"来源 metadata: {docs[0].metadata}")
    print(f"全文长度: {len(docs[0].page_content)} 字符\n")

    # --- Splitter：按 chunk_size / overlap 切分 ---
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    print(f"切分后：{len(chunks)} 个 chunk\n")
    for i, chunk in enumerate(chunks, start=1):
        preview = chunk.page_content.replace("\n", " ")[:80]
        print(f"[chunk {i}] len={len(chunk.page_content)} | {preview}...")


if __name__ == "__main__":
    main()
