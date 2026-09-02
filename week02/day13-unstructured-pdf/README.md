# Week 2 / Day 13 — 复杂 PDF / Unstructured

> **状态**：`available`  
> **长文教程**（可选）：[用 Unstructured 解析含表格的复杂 PDF](../../notes/week02/day13-unstructured-pdf.md)

## 今日目标

对比 PyPDF 局限；用 Unstructured `partition_pdf` 解析含表格 PDF；fast vs hi_res；Element → Document → Splitter。

## 前置

- Day 3 分块策略
- Python 3.12+；网络（HF 版面模型）；可选 `export HF_ENDPOINT=https://hf-mirror.com`

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `scripts/generate_sample_pdfs.py` | **第 0 步**：生成 `data/*.pdf` 样例 |
| `data/simple_two_page.pdf` | 简单两页 PDF |
| `data/complex_sample.pdf` | 含表格的复杂 PDF |
| `data/with_image_sample.pdf` | 含图片占位（扩展） |
| `step01_pypdf_limitation.py` | **第 1 步**：PyPDF 在复杂 PDF 上的局限 |
| `demo_partition_pdf.py` | **第 2 步**：`partition_pdf` → Element 类型列表 |
| `demo_elements_inspect.py` | **第 3 步**：fast vs hi_res；Table 元素 |
| `demo_load_and_split.py` | **第 4 步**：Table 用 `text_as_html` → 行列文本 → 分块 |
| `step_remediation_images.py` | 可选：图片/OCR 边界（非主路径） |
| `pyproject.toml` / `uv.lock` | unstructured、pypdf |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 0 | `uv sync` | 依赖较大 |
| 1 | `scripts/generate_sample_pdfs.py` | 生成 PDF |
| 2 | `step01_pypdf_limitation.py` | 感受 PyPDF 丢结构 |
| 3 | `demo_partition_pdf.py` | Unstructured 元素类型 |
| 4 | `demo_elements_inspect.py` | hi_res 首次较慢（下模型） |
| 5 | `demo_load_and_split.py` | 接入 RAG 分块流水线 |

## 验收命令（汇总）

```bash
cd week02/day13-unstructured-pdf

uv sync
uv run python scripts/generate_sample_pdfs.py
uv run python step01_pypdf_limitation.py
uv run python demo_partition_pdf.py
uv run python demo_elements_inspect.py
uv run python demo_load_and_split.py
```

## 验收标准

- `hi_res` + `infer_table_structure=True` 出现 `Table` 类型
- `demo_load_and_split` 优先用表格 HTML 转行列文本再切分

## 收工清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
