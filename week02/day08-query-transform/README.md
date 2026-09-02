# Week 2 / Day 8 — Query Transformation

> **状态**：`available`
> 对外文章：[检索前先改写问句：Multi-Query 与 HyDE](../../notes/week02/day08-query-transform.md)

## 怎么学

按文章自学；不要一次跑完全部脚本。

## 验收命令

```bash
cd week02/day08-query-transform
uv sync
cp .env.example .env   # 按需改模型名

uv run python step01_retrieval_gap.py
uv run python demo_multi_query.py
uv run python demo_hyde.py
uv run python demo_rag_with_transform.py --mode none
uv run python demo_rag_with_transform.py --mode multi_query
uv run python demo_rag_with_transform.py --mode hyde
```

**需要**：本机 Ollama 已启动（默认 `qwen2:7b`）。
