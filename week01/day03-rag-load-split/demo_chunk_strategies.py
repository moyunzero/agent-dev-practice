"""Day3 补全：对比 MD/PDF 加载与多种分块策略（上游强制目标）。"""

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

DATA_DIR = Path(__file__).parent / "data"
MD = DATA_DIR / "sample.md"
PDF = DATA_DIR / "sample.pdf"


def load_md() -> str:
    docs = TextLoader(str(MD), encoding="utf-8").load()
    return docs[0].page_content


def strategy_a_recursive_on_md(text: str):
    """策略 A：按字符递归切（通用，不区分标题结构）。"""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    )
    return splitter.split_text(text)


def strategy_b_markdown_headers(text: str):
    """策略 B：按 Markdown 标题切（保留章节语义，适合 MD 手册/笔记）。"""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            # ("#", "h1"),
            ("##", "h2"),
        ]
    )
    return header_splitter.split_text(text)


def strategy_c_pdf_by_page_then_chars():
    """策略 C：PDF 先按页加载，再对每页做字符切分。"""
    page_docs = PyPDFLoader(str(PDF)).load()
    splitter = RecursiveCharacterTextSplitter(chunk_size=120, chunk_overlap=20)
    chunks = []
    for doc in page_docs:
        page_chunks = splitter.split_documents([doc])
        chunks.extend(page_chunks)
    return page_docs, chunks


def print_chunks(title: str, chunks, show_meta: bool = False) -> None:
    print(f"\n=== {title}：共 {len(chunks)} 块 ===")
    for i, chunk in enumerate(chunks, start=1):
        if show_meta and hasattr(chunk, "metadata"):
            meta = chunk.metadata
            body = chunk.page_content
        elif isinstance(chunk, dict):
            meta = {k: v for k, v in chunk.metadata.items()} if hasattr(chunk, "metadata") else chunk.get("metadata", {})
            body = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
        else:
            meta = getattr(chunk, "metadata", {})
            body = chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
        preview = body.replace("\n", " ")[:70]
        if show_meta and meta:
            print(f"[{i}] meta={meta} | {preview}...")
        else:
            print(f"[{i}] {preview}...")


def main() -> None:
    md_text = load_md()
    print("已加载 MD，长度:", len(md_text), "字符")

    chunks_a = strategy_a_recursive_on_md(md_text)
    print_chunks("策略 A · MD · RecursiveCharacter（按长度+分隔符）", chunks_a)

    chunks_b = strategy_b_markdown_headers(md_text)
    print_chunks("策略 B · MD · MarkdownHeader（按 # / ## 标题）", chunks_b, show_meta=True)

    page_docs, chunks_c = strategy_c_pdf_by_page_then_chars()
    print(f"\n=== 策略 C · PDF · PyPDFLoader（{len(page_docs)} 页）+ RecursiveCharacter ===")
    print(f"切分后共 {len(chunks_c)} 块")
    for i, chunk in enumerate(chunks_c, start=1):
        page = chunk.metadata.get("page", "?")
        preview = chunk.page_content[:70].replace("\n", " ")
        print(f"[{i}] page={page} | {preview}...")

    print(
        """

【策略怎么选 —— 上游「分块策略」要掌握的部分】
1. MD + 有清晰标题结构 → 优先 MarkdownHeaderTextSplitter（一块≈一节，metadata 带 h1/h2）
2. 纯文本 / 结构乱 / 英文 PDF 段落 → RecursiveCharacterTextSplitter（调 chunk_size/overlap）
3. PDF → 先用 PyPDFLoader 按页读出，再对每页 split（扫描版 PDF 需 OCR，另论）
4. chunk_size 变大 → 块数变少；chunk_overlap → 相邻块故意重复，防截断丢语义
"""
    )


if __name__ == "__main__":
    main()
