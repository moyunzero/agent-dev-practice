"""生成 demo 用的 sample.pdf（仅练习仓内使用）。"""

from pathlib import Path

from fpdf import FPDF

out = Path(__file__).parent / "data" / "sample.pdf"
out.parent.mkdir(parents=True, exist_ok=True)

pdf = FPDF()
pdf.set_font("Helvetica", size=12)

pdf.add_page()
pdf.multi_cell(
    0,
    8,
    "Page 1 - FastAPI is a Python web framework for building APIs. "
    "It uses type hints and auto-generates OpenAPI docs. "
    "PyPDFLoader usually returns one Document per page.",
)

pdf.add_page()
pdf.multi_cell(
    0,
    8,
    "Page 2 - RAG loads documents, splits them into chunks, embeds chunks, "
    "retrieves relevant chunks, and injects them into the prompt. "
    "Metadata page index starts at 0.",
)

pdf.output(str(out))
print(f"已写入 {out}")
