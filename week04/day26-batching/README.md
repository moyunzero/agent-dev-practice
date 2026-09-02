# Week 4 / Day 26 — Embedding 与 Rerank 批处理

> **状态**：`available`
> 对外文章：[给 Embedding 和 Rerank 做批处理：一次干一捆，提高吞吐](../../notes/week04/day26-batching.md)

## 验收命令

```bash
cd week04/day26-batching
uv sync
uv run python step01_batch_intuition.py
uv run python step02_embed_batch.py
uv run python step03_rerank_batch.py
```

**期望**：玩具脚本一批远快于逐条；真模型在条数够时一批吞吐更高。万级建库用 `embed_chunked.py` 分批，勿一次塞爆内存。

## 收工清理

```bash
rm -rf .venv __pycache__
```
