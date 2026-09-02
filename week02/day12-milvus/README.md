# Week 2 / Day 12 — Milvus 向量库

> **状态**：`available`  
> **长文教程**（可选）：[用 Docker 部署 Milvus 并跑通 Python SDK](../../notes/week02/day12-milvus.md)

## 今日目标

Docker 起 Milvus Standalone；pymilvus 建表、CRUD、Top-K；RAG 半链路（带 `text` 字段）。

## 前置

- Docker Desktop
- Day 4 Embedding 概念（384 维向量）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `docker-compose.yml` | **第 0 步**：Milvus Standalone（宿主机端口 **19531**） |
| `milvus_config.py` | 连接 URI、collection 名等 |
| `data/sample.md` | RAG 样例文档 |
| `step01_check_milvus.py` | **第 1 步**：连通性、版本、collections 列表 |
| `demo_create_collection.py` | **第 2 步**：建 collection（id + embedding） |
| `demo_crud.py` | **第 3 步**：insert / search / delete + flush |
| `demo_rag_search.py` | **第 4 步**：带 `text` 字段的 RAG 半链路 Top-K |
| `pyproject.toml` / `uv.lock` | pymilvus |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `docker compose up -d` && `docker compose ps` | standalone **healthy** |
| 1 | `uv sync` | Python 依赖 |
| 2 | `step01_check_milvus.py` | 版本 v2.4.x |
| 3 | `demo_create_collection.py` | collection 创建成功 |
| 4 | `demo_crud.py` | Insert 2 条；问句 Top-1；Delete 后剩 1 条 |
| 5 | `demo_rag_search.py` | Top-K + `text` 预览 |

## 验收命令（汇总）

```bash
cd week02/day12-milvus

docker compose down   # 若上次失败，先清再起
docker compose up -d
docker compose ps

uv sync
uv run python step01_check_milvus.py
uv run python demo_create_collection.py
uv run python demo_crud.py
uv run python demo_rag_search.py
```

**默认 URI**：`http://127.0.0.1:19531`  
复用本机已有 Milvus（19530）：`MILVUS_PORT=19530 uv run python step01_check_milvus.py`

## 验收标准

- Docker standalone healthy
- CRUD + Top-K 问句 `ERR_CHUNK_42 怎么处理？` 命中 id=2
- `demo_rag_search` 通过 `output_fields=["text"]` 取回正文

## 收工清理

```bash
docker compose down
rm -rf .venv __pycache__
```
