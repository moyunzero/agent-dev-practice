"""第 1 课：PyPDFLoader 在「复杂 PDF」上的局限 — 对比简单页 vs 含表格页。"""

from __future__ import annotations

from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader

DATA = Path(__file__).parent / "data"
SIMPLE_PDF = DATA / "simple_two_page.pdf"
COMPLEX_PDF = DATA / "complex_sample.pdf"


def show_pages(label: str, path: Path) -> None:
    print(f"\n=== {label} · {path.name} ===")
    if not path.exists():
        print(f"  （文件不存在，请先生成: uv run python scripts/generate_sample_pdfs.py）")
        return
    docs = PyPDFLoader(str(path)).load()
    print(f"  页数: {len(docs)}")
    for i, doc in enumerate(docs):
        preview = doc.page_content.replace("\n", " ")[:120]
        print(f"  [page {doc.metadata.get('page', i)}] {preview}...")


def main() -> None:
    print("=== Day13 第 1 课：为什么需要 Unstructured？===\n")
    print("Day3 用的 PyPDFLoader：按 PDF 文本流逐页抽取，快、零版面分析。")
    print("复杂 PDF（表格、多栏）常见问题：")
    print("  · 表格 → 列对齐丢失，变成一行乱字符")
    print("  · 图片 → 通常抽不到文字")
    print("  · 多栏 → 阅读顺序可能错\n")

    show_pages("简单 PDF（Day3 同款）", SIMPLE_PDF)
    show_pages("复杂 PDF（含表格）", COMPLEX_PDF)

    print(
        """
【本课要点】
1. PyPDFLoader 适合「有清晰文字层、结构简单」的 PDF。
2. 含表格/版面的 PDF 需要 Unstructured 等工具做元素级解析。
3. 下节课：安装 Unstructured，用 partition_pdf 看 Table / Title 等元素。
"""
    )


if __name__ == "__main__":
    main()
