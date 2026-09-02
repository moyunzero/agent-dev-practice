# Week 1 / Day 3 — RAG 加载与分割

> **状态**：`available`  
> **长文教程**（可选）：[掌握 MD/PDF 加载与文本分块策略](../../notes/week01/day03-rag-load-split.md)

## 今日目标

用 Document Loader 加载 MD/PDF；对比 RecursiveCharacter 与 MarkdownHeader 等分块策略；理解 `chunk_size` / `chunk_overlap`。

## 前置

- Day 2 的 LangChain 基础
- 无需 Ollama（本日纯文档处理）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/sample.md` | 练习用 Markdown 样例 |
| `data/sample.pdf` | 练习用 PDF（可由脚本生成） |
| `prepare_sample_pdf.py` | **第 0 步**：首次生成 2 页 `data/sample.pdf` |
| `step01_document_anatomy.py` | **第 1 步**：Document 结构（`page_content` + `metadata`） |
| `demo_load_split.py` | **第 2 步**：MD 加载 + 基础切分 |
| `demo_chunk_strategies.py` | **第 3 步**：多策略对比（Recursive vs MarkdownHeader vs PDF） |
| `demo_load_pdf.py` | **第 4 步**：PyPDFLoader 按页加载 |
| `main.py` | 可选汇总入口（非主验收路径） |
| `pyproject.toml` / `uv.lock` | langchain、pypdf 等 |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 安装依赖 |
| 1 | `uv run python prepare_sample_pdf.py` | 生成 PDF（仅首次需要） |
| 2 | `uv run python step01_document_anatomy.py` | Document 字段讲解 |
| 3 | `uv run python demo_load_split.py` | MD → chunk 列表 |
| 4 | `uv run python demo_chunk_strategies.py` | **核心**：同文档不同策略块数不同 |
| 5 | `uv run python demo_load_pdf.py` | PDF 按页 + 切分 |

## 验收命令（汇总）

```bash
uv run python prepare_sample_pdf.py   # 首次
uv run python step01_document_anatomy.py
uv run python demo_load_split.py
uv run python demo_chunk_strategies.py
uv run python demo_load_pdf.py
```

## 验收标准

- MD：`TextLoader` → Document；Recursive 与 MarkdownHeader **块数不同**且能解释原因
- PDF：`PyPDFLoader` → 按页 Document；metadata 含 `page`
- 能讲清 `chunk_size` / `chunk_overlap` / 策略如何选型

## 收工清理

```bash
rm -rf .venv __pycache__
```
