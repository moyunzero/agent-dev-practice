# Week 1 / Day 3 — RAG 加载与分割

> **状态**：`available`
> 对外文章：[掌握 MD/PDF 加载与文本分块策略](../../notes/week01/day03-rag-load-split.md)

## 跑起来

```bash
uv run python prepare_sample_pdf.py   # 首次：生成 2 页 sample.pdf
uv run python step01_document_anatomy.py
uv run python demo_load_split.py
uv run python demo_chunk_strategies.py
uv run python demo_load_pdf.py
```

## 验收标准

- MD：`TextLoader` → 1 Document；Recursive 与 MarkdownHeader 块数不同且能解释
- PDF：`PyPDFLoader` → 按页 Document；页内 Recursive 切分；metadata 含 `page`
- 能讲清 `chunk_size` / `chunk_overlap` / 策略选型
