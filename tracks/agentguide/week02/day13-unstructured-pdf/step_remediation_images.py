"""Day13 补洞第 1 课：带图 PDF + 元素类型；对照 MinerU / OCR 边界。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from unstructured.partition.pdf import partition_pdf

DATA = Path(__file__).parent / "data"
PDF = DATA / "with_image_sample.pdf"


def main() -> None:
    if not PDF.exists():
        raise SystemExit("请先: uv run python scripts/generate_sample_pdfs.py")

    print("=== Day13 补洞：含嵌入图的 PDF ===\n")
    print(f"文件: {PDF.name}\n")

    print("--- strategy=fast（偏文本抽取）---")
    fast = partition_pdf(filename=str(PDF), strategy="fast")
    print("类型计数:", dict(Counter(type(el).__name__ for el in fast)))
    for i, el in enumerate(fast, 1):
        print(f"  [{i}] {type(el).__name__:16} | {str(el).replace(chr(10), ' ')[:70]}")

    print("\n--- strategy=hi_res（版面；可能更慢，首次或下模型）---")
    try:
        hi = partition_pdf(filename=str(PDF), strategy="hi_res")
        print("类型计数:", dict(Counter(type(el).__name__ for el in hi)))
        for i, el in enumerate(hi, 1):
            print(f"  [{i}] {type(el).__name__:16} | {str(el).replace(chr(10), ' ')[:70]}")
        images = [el for el in hi if "Image" in type(el).__name__ or "Figure" in type(el).__name__]
        print(f"\nImage/Figure 类数量: {len(images)}")
    except Exception as e:  # noqa: BLE001
        print(f"hi_res 未跑通（依赖/模型）：{e}")
        print("仍可用 fast 结果 + 下文边界对照完成概念过关。")

    print(
        """
【补洞要点】
1. 上游目标含「表格、图片」：表格已在原 Day13 练过；本课补「带图 PDF」。
2. 有文字层 + 嵌入图：解析器可能产出 Image/Figure；图里的字不一定进文本。
3. 纯扫描页（整页是图、无文字层）：必须 OCR；Unstructured 开 OCR，或换 MinerU 等重型方案。
4. MinerU：偏学术/复杂版面/公式；不是「每天必装」，但要知道何时比通用 Unstructured 更合适。
"""
    )


if __name__ == "__main__":
    main()
