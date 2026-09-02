# Week 2 / Day 14 — RAG 系统升级

> **状态**：`available`  
> **长文教程**（可选）：[把 Week1 Naive RAG 升级成 Hybrid + Rerank + Milvus](../../notes/week02/day14-rag-upgrade.md)

## 今日目标

Milvus 入库 + BM25∥向量 RRF + CrossEncoder Rerank；Naive vs Upgraded 三档对照；FastAPI `/ask`。

## 前置

- Day 9 Hybrid、Day 12 Milvus
- Docker + Ollama（生成可选）

## 文件说明

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | Milvus Standalone（19531） |
| `milvus_config.py` | Milvus 连接配置 |
| `data/sample.md` | 索引文档 |
| `step01_pipeline_map.py` | **第 1 步**：Naive vs 升级流水线 ASCII/对照 |
| `demo_index_milvus.py` | **第 2 步**：chunk → Milvus（含 text 字段） |
| `demo_hybrid_milvus.py` | **第 3 步**：BM25 + Milvus 向量 → RRF |
| `demo_upgraded_rag.py` | **第 4 步**：Naive / Hybrid / +Rerank CLI 三档 |
| `upgraded_pipeline.py` | **模块**：可复用的升级检索 + 可选 Ollama 生成 |
| `main_api.py` | **第 5 步**：FastAPI `/health`、`POST /ask` |
| `pyproject.toml` / `uv.lock` | pymilvus、rank_bm25、sentence-transformers |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `docker compose up -d` | Milvus healthy |
| 1 | `uv sync` | 依赖 |
| 2 | `step01_pipeline_map.py` | 流水线差异 |
| 3 | `demo_index_milvus.py` | 数据入库 |
| 4 | `demo_hybrid_milvus.py` | 混合检索 Top-K |
| 5 | `demo_upgraded_rag.py` | 三档 Top-1 对比 |
| 6 | `uvicorn main_api:app --port 8014` | HTTP API |
| 7 | curl `/ask` | `pipeline: milvus+bm25/rrf+rerank` |

## 验收命令（汇总）

```bash
cd week02/day14-rag-upgrade

docker compose up -d
docker compose ps

uv sync
uv run python step01_pipeline_map.py
uv run python demo_index_milvus.py
uv run python demo_hybrid_milvus.py
uv run python demo_upgraded_rag.py

uv run uvicorn main_api:app --reload --port 8014
curl -s http://127.0.0.1:8014/health
curl -s -X POST http://127.0.0.1:8014/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"ERR_CHUNK_42 怎么处理？","generate":false}'
```

## 验收标准

- 问句 `ERR_CHUNK_42 怎么处理？`：Hybrid / +Rerank Top-1 为错误码段
- API 响应含 `pipeline: milvus+bm25/rrf+rerank`
- `generate:false` 时 `answer` 为 `(retrieve-only)`

## 收工清理

```bash
docker compose down
rm -rf .venv __pycache__
```
