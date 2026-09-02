# Week 1 / Day 1 — FastAPI Hello

> **状态**：`available`
> 对外文章：[用 FastAPI 搭双后端最小 API](../../notes/week01/day01-fastapi.md)

## 跑起来

```bash
# 确认 Ollama 在跑，且已有模型
ollama list

cp .env.example .env
# 填 OPENROUTER_API_KEY 后再测 openrouter

uv run uvicorn main:app --reload --port 8000
```

## 验收命令

```bash
curl -sS http://127.0.0.1:8000/
curl -sS http://127.0.0.1:8000/health
# 期望含 "service":"day01"
curl -sS http://127.0.0.1:8000/version
curl -sS http://127.0.0.1:8000/items/3
curl -sS 'http://127.0.0.1:8000/search?q=fastapi&limit=2'

curl -sS http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"用一句话介绍 FastAPI","provider":"ollama","temperature":0}'

curl -sS http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"用一句话介绍 FastAPI","provider":"openrouter"}'
```

浏览器：http://127.0.0.1:8000/docs
