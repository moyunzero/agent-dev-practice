# Week 2 / Day 14 — RAG 系统升级

> **状态**：`available`
> 对外文章：[把 Week1 Naive RAG 升级成 Hybrid + Rerank + Milvus](../../notes/week02/day14-rag-upgrade.md)

## 怎么学

按文章自学，或逐脚本跟练。需要 Docker（Milvus）与可选 Ollama。

## 验收命令（全文）

```bash
cd week02/day14-rag-upgrade

docker compose up -d
docker compose ps     # standalone 应为 healthy

uv sync
uv run python step01_pipeline_map.py
uv run python demo_index_milvus.py
uv run python demo_hybrid_milvus.py
uv run python demo_upgraded_rag.py

# 系统形态（补洞）
uv run uvicorn main_api:app --reload --port 8014
curl -s http://127.0.0.1:8014/health
curl -s -X POST http://127.0.0.1:8014/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"ERR_CHUNK_42 怎么处理？","generate":false}'
```

**默认 URI**：`http://127.0.0.1:19531`  
**期望**：问句 `ERR_CHUNK_42 怎么处理？` 时，Hybrid / +Rerank 的 Top-1 为错误码段；仅向量可能偏到分块参数。  
**API**：`pipeline` 应为 `milvus+bm25/rrf+rerank`；`generate:false` 时 `answer` 为 `(retrieve-only)`。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `step01_pipeline_map.py` | Naive vs 升级流水线对照 |
| `demo_index_milvus.py` | chunk → Milvus（带 text） |
| `demo_hybrid_milvus.py` | BM25 ∥ Milvus → RRF |
| `demo_upgraded_rag.py` | Naive / Hybrid / +Rerank；可选 Ollama |
| `upgraded_pipeline.py` | 可复用的升级检索 + 可选生成 |
| `main_api.py` | FastAPI：`/health`、`/ask` |

## 收工后清理

```bash
docker compose down
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
