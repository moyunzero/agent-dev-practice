# Week 1 / Day 5–6 — 手撕 Naive RAG

> **状态**：`available`  
> **长文教程**（可选）：[手撕 Naive RAG 端到端文档问答 API](../../notes/week01/day05-06-naive-rag.md)

## 今日目标

串联 Day 1–4：检索 + LCEL 生成 → `POST /ask` 文档问答 API；返回 `answer` + `sources`。

## 前置

- Day 4 的 Chroma 检索概念
- Ollama 已启动
- 首次 `uv sync` 较慢（Embedding 模型）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/sample.md` | 被索引的文档 |
| `step01_retrieve_and_prompt.py` | **第 1 步**：只做检索 + 拼 prompt（不调用 LLM） |
| `demo_rag_chain.py` | **第 2 步**：CLI 版完整 Naive RAG 链 |
| `main.py` | **第 3 步**：FastAPI `POST /ask`、`GET /health` |
| `chroma_db/` | 向量索引（随 demo 生成） |
| `.env.example` | Ollama / 模型配置 |
| `.dockerignore` | 供 Day 7 Docker 构建忽略规则 |
| `pyproject.toml` / `uv.lock` | FastAPI + LangChain + Chroma |

## 推荐顺序

**不要一次跑完全部。** 按表顺序，每步看懂输出再下一步。

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 安装依赖 |
| 1 | `cp .env.example .env` | 环境就绪 |
| 2 | `uv run python step01_retrieve_and_prompt.py` | 检索到的 chunk + 拼好的 prompt 文本 |
| 3 | `uv run python demo_rag_chain.py` | 终端打印 answer（含 sources 摘要） |
| 4 | `uv run uvicorn main:app --reload --port 8002` | HTTP 服务 |
| 5 | 下方 curl `/ask` | JSON：`answer` + `sources` |

## 验收命令（汇总）

```bash
uv run python step01_retrieve_and_prompt.py
uv run python demo_rag_chain.py
uv run uvicorn main:app --reload --port 8002

curl -s -X POST http://127.0.0.1:8002/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"chunk_overlap 是干什么的？"}'
```

## 验收标准

- `step01` 能看到检索到的 chunk 被填入 prompt 模板
- `/ask` 返回非空 `answer`，`sources` 含 chunk 摘要
- 能口述 Naive RAG 四步：load/index → retrieve → prompt → generate

## 收工清理

```bash
rm -rf .venv __pycache__ chroma_db/
```
