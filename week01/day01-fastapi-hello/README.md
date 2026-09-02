# Week 1 / Day 1 — FastAPI Hello

> **状态**：`available`  
> **长文教程**（可选）：[用 FastAPI 搭双后端最小 API](../../notes/week01/day01-fastapi.md) — 想深入原理再看；**本 README 可独立跟练**

## 今日目标

跑通最小 FastAPI 服务：路由（path / query / body）、`/health`，以及通过 Ollama / OpenRouter 调大模型的 `/chat`。

## 前置

- Python 3.12+、[uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) 已启动且已 pull 模型（如 `qwen2:7b`）
- OpenRouter 可选：填 `.env` 里的 `OPENROUTER_API_KEY`

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `main.py` | **主入口**：FastAPI 应用；`GET /`、`/health`、`/items/{id}`、`/search`、`POST /chat` 等 |
| `pyproject.toml` / `uv.lock` | 依赖声明与锁定（FastAPI、OpenAI SDK、uvicorn） |
| `.env.example` | 环境变量模板；复制为 `.env` |
| `.python-version` | 推荐 Python 3.12 |

## 推荐顺序

| 步骤 | 做什么 | 命令 |
|:----:|--------|------|
| 0 | 安装依赖 | `uv sync` |
| 1 | 准备环境变量 | `cp .env.example .env`（纯 Ollama 可不填 Key） |
| 2 | 确认 Ollama | `ollama list` |
| 3 | 启动 API | `uv run uvicorn main:app --reload --port 8000` |
| 4 | 浏览器看文档 | 打开 http://127.0.0.1:8000/docs |
| 5 | 终端验收 | 见下方「验收命令」 |

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

## 验收标准

- `/docs` 能打开，接口列表完整
- `GET /health` 返回 `status: ok`
- `POST /chat` + `provider=ollama` 有模型回复
- （可选）OpenRouter 同样能回复

## 收工清理

```bash
rm -rf .venv __pycache__
```
