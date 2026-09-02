# Week 1 / Day 4 — RAG 向量化与存储

> **状态**：`available`
> 对外文章：[理解 Embedding 并用 Chroma 构建本地向量索引](../../notes/week01/day04-rag-embed-store.md)

## 验收命令

```bash
uv run python step01_cosine_intuition.py
uv run python step02_embed_texts.py
uv run python demo_index_chunks.py
uv run python demo_search.py
uv run python demo_rag_retrieve.py
```

## 验收标准

- 能说清 Embedding / Vector Store / Top-K
- Chroma 入库 4 条 chunk；问句检索返回带 score 的 Document
- 全链路：load → split → embed → store → search
