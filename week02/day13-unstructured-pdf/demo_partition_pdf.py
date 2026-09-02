"""第 2 课：Unstructured partition_pdf — 元素级解析 vs PyPDF 整页文本。"""

from __future__ import annotations

from pathlib import Path

from unstructured.partition.pdf import partition_pdf

DATA = Path(__file__).parent / "data"
COMPLEX_PDF = DATA / "complex_sample.pdf"


def main() -> None:
    if not COMPLEX_PDF.exists():
        raise SystemExit("请先运行: uv run python scripts/generate_sample_pdfs.py")

    print("=== Day13 第 2 课：partition_pdf ===\n")
    print(f"文件: {COMPLEX_PDF.name}")
    print("strategy=fast（有文字层的 PDF，pdfminer 抽取 + 元素分类）\n")

    elements = partition_pdf(
        filename=str(COMPLEX_PDF),
        strategy="fast",
        infer_table_structure=True,
    )

    print(f"共 {len(elements)} 个 element:\n")
    for i, el in enumerate(elements, 1):
        kind = type(el).__name__
        text = str(el).replace("\n", " ")[:100]
        print(f"  [{i}] {kind:16} | {text}...")

    kinds = {}
    for el in elements:
        name = type(el).__name__
        kinds[name] = kinds.get(name, 0) + 1
    print(f"\n类型统计: {kinds}")

    print(
        """
【本课要点】
1. partition_pdf 返回 Element 列表，不是「一页一个 Document」。
2. 常见类型：Title、NarrativeText、Table、Footer…（见输出 class 名）。
3. infer_table_structure=True 会尝试保留表格结构（strategy 可能升到 hi_res）。
4. 下节课：专门看 Table 元素内容与 metadata。
"""
    )


if __name__ == "__main__":
    main()
