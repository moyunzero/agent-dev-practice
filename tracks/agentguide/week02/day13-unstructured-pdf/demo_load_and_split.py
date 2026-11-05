"""第 4 课：接入 RAG 半链路 — elements → Document → split，对比 Day3 PyPDF。"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from unstructured.partition.pdf import partition_pdf

DATA = Path(__file__).parent / "data"
COMPLEX_PDF = DATA / "complex_sample.pdf"

SPLITTER = RecursiveCharacterTextSplitter(
    chunk_size=100,
    chunk_overlap=40,
    separators=["\n\n", "\n", "。", " ", ""],
)


class _TableToPipes(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            self._in_cell = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            self._row.append("".join(self._cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._row:
            self.rows.append(self._row)

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def html_table_to_pipes(html: str) -> str:
    parser = _TableToPipes()
    parser.feed(html)
    return "\n".join(" | ".join(row) for row in parser.rows if any(row))


def element_text(el) -> str:
    html = getattr(getattr(el, "metadata", None), "text_as_html", None)
    if type(el).__name__ == "Table" and html:
        return html_table_to_pipes(html)
    return str(el)


def elements_to_documents(elements) -> list[Document]:
    """Unstructured Element → LangChain Document（metadata 带元素类型）。"""
    docs: list[Document] = []
    for el in elements:
        meta = {"category": type(el).__name__}
        page = getattr(getattr(el, "metadata", None), "page_number", None)
        if page is not None:
            meta["page"] = page
        docs.append(Document(page_content=element_text(el), metadata=meta))
    return docs


def show_chunks(label: str, chunks: list[Document]) -> None:
    print(f"\n=== {label} · 共 {len(chunks)} 块 ===")
    for i, doc in enumerate(chunks, 1):
        cat = doc.metadata.get("category", doc.metadata.get("page", "?"))
        preview = doc.page_content.replace("\n", " ")[:85]
        print(f"  [{i}] meta={cat} | {preview}...")


def main() -> None:
    if not COMPLEX_PDF.exists():
        raise SystemExit("请先运行: uv run python scripts/generate_sample_pdfs.py")

    print("=== Day13 第 4 课：接入 Day3/Day4 分块流程 ===\n")
    print("链路：解析 → List[Document] → RecursiveCharacterTextSplitter → chunks → (Day4 embed)")

    pypdf_docs = PyPDFLoader(str(COMPLEX_PDF)).load()
    pypdf_chunks = SPLITTER.split_documents(pypdf_docs)
    show_chunks("PyPDFLoader → split", pypdf_chunks)

    elements = partition_pdf(
        filename=str(COMPLEX_PDF),
        strategy="hi_res",
        infer_table_structure=True,
    )
    uns_docs = elements_to_documents(elements)
    uns_chunks = SPLITTER.split_documents(uns_docs)
    show_chunks("Unstructured hi_res → split", uns_chunks)

    table_docs = [d for d in uns_docs if d.metadata.get("category") == "Table"]
    table_chunks = SPLITTER.split_documents(table_docs) if table_docs else []
    show_chunks("仅 Table 元素 → split", table_chunks)

    print(
        """
【本课要点】
1. Unstructured 解析后要先转成 LangChain Document，才能复用 Day3 Splitter。
2. metadata.category（Title/Table/…）可用来过滤、加权或单独建索引。
3. Table 优先用 metadata.text_as_html 转成行列文本，再 embed。
4. 下游不变：chunks → HuggingFaceEmbeddings → Chroma/Milvus（Day4/Day12）。
"""
    )


if __name__ == "__main__":
    main()
