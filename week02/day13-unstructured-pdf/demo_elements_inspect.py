"""第 3 课：fast vs hi_res — 表格元素 Table 与 metadata。"""

from __future__ import annotations

from pathlib import Path

from unstructured.partition.pdf import partition_pdf

DATA = Path(__file__).parent / "data"
COMPLEX_PDF = DATA / "complex_sample.pdf"


def show_elements(label: str, strategy: str, infer_table: bool) -> list:
    print(f"\n=== {label} · strategy={strategy!r} · infer_table_structure={infer_table} ===")
    elements = partition_pdf(
        filename=str(COMPLEX_PDF),
        strategy=strategy,
        infer_table_structure=infer_table,
    )
    kinds: dict[str, int] = {}
    for el in elements:
        name = type(el).__name__
        kinds[name] = kinds.get(name, 0) + 1
    print(f"  共 {len(elements)} 个 element · 类型: {kinds}")

    for i, el in enumerate(elements, 1):
        kind = type(el).__name__
        preview = str(el).replace("\n", " ")[:90]
        print(f"  [{i}] {kind:16} | {preview}...")

    tables = [el for el in elements if type(el).__name__ == "Table"]
    if tables:
        print("\n  --- Table 元素详情（第 1 个）---")
        t = tables[0]
        print(f"  metadata: {getattr(t, 'metadata', None)}")
        text = str(t)
        print(f"  content 前 300 字:\n{text[:300]}")
    else:
        print("\n  （本策略未识别出 Table 类；表格可能被拆成 Title/NarrativeText）")

    return elements


def main() -> None:
    if not COMPLEX_PDF.exists():
        raise SystemExit("请先运行: uv run python scripts/generate_sample_pdfs.py")

    print("=== Day13 第 3 课：表格与 strategy ===\n")
    print("第 2 课 fast：表格常拆散 → 无 Table 类")
    print("hi_res + infer_table_structure：版面模型尝试还原表格\n")

    show_elements("快路径", "fast", infer_table=False)
    show_elements("版面+表格", "hi_res", infer_table=True)

    print(
        """
【本课要点】
1. fast = pdfminer 抽文本 + 规则分类，快但表格易碎。
2. hi_res = 版面检测模型，infer_table_structure=True 时更可能产出 Table 元素。
3. Table 元素常带 HTML/Markdown 结构，比 PyPDF 一行乱字更适合 RAG chunk。
4. 下节课：elements → LangChain Document → split，对比 Day3 分块。
"""
    )


if __name__ == "__main__":
    main()
