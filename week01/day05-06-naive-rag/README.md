# Week 1 / Day 5–6 — 手撕 Naive RAG

> **状态**：`available`
> 对外文章：[手撕 Naive RAG 端到端文档问答 API](../../notes/week01/day05-06-naive-rag.md)

## 怎么学

**不要一次跑完全部。** 建议按文章顺序：原理 → 动手 → 自检后再下一课。

## 验收命令

```bash
uv run python step01_retrieve_and_prompt.py
uv run python demo_rag_chain.py
uv run uvicorn main:app --reload --port 8002
curl -s -X POST http://127.0.0.1:8002/ask -H "Content-Type: application/json" -d '{"question":"chunk_overlap 是干什么的？"}'
```
