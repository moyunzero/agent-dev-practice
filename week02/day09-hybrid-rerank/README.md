# Week 2 / Day 9 — 混合检索与 Rerank

> **状态**：`available`
> 对外文章：[BM25 + 向量混合检索与 Rerank](../../notes/week02/day09-hybrid-rerank.md)

## 怎么学

按文章自学；不要一次跑完全部脚本。

## 验收命令

```bash
cd week02/day09-hybrid-rerank
uv sync

uv run python step01_keyword_vs_semantic.py
uv run python demo_bm25.py
uv run python demo_hybrid_rrf.py
uv run python demo_rerank.py
uv run python demo_pipeline_compare.py
```

**需要**：首次运行会下载 Embedding / CrossEncoder 模型（可复用 HF 缓存）。
