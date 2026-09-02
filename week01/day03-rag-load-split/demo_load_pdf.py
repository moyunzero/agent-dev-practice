"""Day3 第 2 课：加载 PDF + 同样用 Splitter 分块。"""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

PDF = Path(__file__).parent / "data" / "sample.pdf"


def main() -> None:
    docs = PyPDFLoader(str(PDF)).load()
    print(f"加载完成：{len(docs)} 个 Document（通常每页一个）")
    print(f"第 1 页 metadata: {docs[0].metadata}")
    print(f"第 1 页内容预览: {docs[0].page_content[:120]}...\n")

    splitter = RecursiveCharacterTextSplitter(chunk_size=120, chunk_overlap=20)
    chunks = splitter.split_documents(docs)
    print(f"切分后：{len(chunks)} 个 chunk\n")
    for i, chunk in enumerate(chunks, start=1):
        print(f"[chunk {i}] len={len(chunk.page_content)} | {chunk.page_content[:100]}...")


if __name__ == "__main__":
    main()
