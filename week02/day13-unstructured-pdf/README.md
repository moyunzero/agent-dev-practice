# Week 2 / Day 13 — 复杂 PDF / Unstructured

> **状态**：`available`
> 对外文章：[用 Unstructured 解析含表格的复杂 PDF](../../notes/week02/day13-unstructured-pdf.md)

## 怎么学

按文章自学，或逐脚本跟练。第 1 课先对比 PyPDF 局限，再引入 Unstructured。

## 验收命令（全文）

```bash
cd week02/day13-unstructured-pdf

uv sync
uv run python scripts/generate_sample_pdfs.py

# 1. PyPDF 局限
uv run python step01_pypdf_limitation.py

# 2. partition_pdf（fast）
uv run python demo_partition_pdf.py

# 3. fast vs hi_res（首次 hi_res 会下版面模型，较慢）
uv run python demo_elements_inspect.py

# 4. Element → Document → split（Table 优先 text_as_html）
uv run python demo_load_and_split.py
```

**需要**：Python 3.12+、网络（HF 模型）；可选 `export HF_ENDPOINT=https://hf-mirror.com`。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `scripts/generate_sample_pdfs.py` | 生成含表格的 `complex_sample.pdf` |
| `step01_pypdf_limitation.py` | PyPDF 对照简单/复杂 PDF |
| `demo_partition_pdf.py` | `partition_pdf` Element 类型 |
| `demo_elements_inspect.py` | fast vs hi_res + Table |
| `demo_load_and_split.py` | 接入 Day3 Splitter；`text_as_html` → 行列文本 |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
