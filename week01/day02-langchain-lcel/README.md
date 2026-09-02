# Week 1 / Day 2 — LangChain 六大模块 + LCEL

> **状态**：`available`
> 对外文章：[理解六大模块并熟练 LCEL](../../notes/week01/day02-langchain-lcel.md)

## 跑起来

```bash
cp .env.example .env

uv run python demo_lcel.py
uv run python demo_memory.py
uv run python demo_modules_map.py

uv run uvicorn main:app --reload --port 8001
curl -sS http://127.0.0.1:8001/chain \
  -H 'Content-Type: application/json' \
  -d '{"question":"FastAPI 是什么？","provider":"ollama"}'
```

文档：http://127.0.0.1:8001/docs
