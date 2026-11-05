"""生成教学用 PDF：simple_two_page + complex_sample（表格）+ with_image_sample（嵌入图）。"""

from __future__ import annotations

import shutil
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DAY3_SIMPLE = ROOT.parent.parent / "week01" / "day03-rag-load-split" / "data" / "sample.pdf"
PNG = DATA / "diagram_placeholder.png"


def copy_simple_pdf() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "simple_two_page.pdf"
    if DAY3_SIMPLE.exists():
        shutil.copy(DAY3_SIMPLE, out)
        print(f" copied Day3 sample → {out}")
    else:
        print(f" skip simple: {DAY3_SIMPLE} not found")


def write_complex_sample() -> None:
    out = DATA / "complex_sample.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    table_data = [
        ["Code", "Meaning", "Fix"],
        ["ERR_CHUNK_42", "Index out of sync with source docs", "Stop writes → rebuild collection → re-embed all"],
        ["ERR_EMBED_DIM", "Vector dim != schema dim", "Check embedding model vs Milvus dim"],
    ]
    t = Table(table_data, colWidths=[90, 140, 220])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story = [
        Paragraph("RAG Ops Manual · Error Code Reference", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "When the vector index is stale after source doc updates, queries may return inconsistent results.",
            styles["Normal"],
        ),
        Spacer(1, 12),
        t,
        Spacer(1, 12),
        Paragraph(
            "Rule: stop writes → clear or rebuild index → re-embed all chunks → reopen search.",
            styles["Normal"],
        ),
    ]
    doc.build(story)
    print(f" wrote {out}")


def write_with_image_sample() -> None:
    """含嵌入位图的 PDF：补洞用，对照「表格 PDF」与「带图 PDF」。"""
    out = DATA / "with_image_sample.pdf"
    if not PNG.exists():
        raise SystemExit(f"缺少 {PNG}，请先准备 diagram_placeholder.png")
    doc = SimpleDocTemplate(str(out), pagesize=letter)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("RAG Ops Manual · Architecture Sketch", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "Below is an embedded diagram (PNG). Text extractors may see an Image element; "
            "scanned pages with NO text layer need OCR (or tools like MinerU).",
            styles["Normal"],
        ),
        Spacer(1, 12),
        Image(str(PNG), width=120, height=120),
        Spacer(1, 12),
        Paragraph(
            "Caption: placeholder architecture block. For RAG, decide: store OCR text, "
            "caption only, or multimodal embedding.",
            styles["Normal"],
        ),
    ]
    doc.build(story)
    print(f" wrote {out}")


def main() -> None:
    copy_simple_pdf()
    write_complex_sample()
    write_with_image_sample()


if __name__ == "__main__":
    main()
