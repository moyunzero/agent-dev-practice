# Week 2 / Day 12 — Milvus 向量库

> **状态**：`available`
> 对外文章：[用 Docker 部署 Milvus 并跑通 Python SDK](../../notes/week02/day12-milvus.md)

## 怎么学

按文章自学，或逐脚本跟练。第 1 课先起 Docker，再跑连通性脚本。

## 验收命令（全文）

```bash
cd week02/day12-milvus

# 1. 起 Milvus Standalone（需 Docker Desktop）
docker compose down   # 若上次失败，先清再起
docker compose up -d
docker compose ps     # standalone 应为 healthy

# 2. Python 依赖
uv sync

# 3. 连通性
uv run python step01_check_milvus.py
# 期望：Milvus 版本 v2.4.15，collections 列表

# 4. 建 collection
uv run python demo_create_collection.py

# 5. CRUD + Top-K
uv run python demo_crud.py
# 期望：Insert 2 条；ERR_CHUNK_42 问句 Top-1 为 id=2；Delete 后剩 1 条

# 6. RAG 半链路（带 text 字段）
uv run python demo_rag_search.py
# 期望：索引 2 chunk；两问句均有 Top-K + text 预览
```

**默认 URI**：`http://127.0.0.1:19531`（宿主机端口，避免与已有 Milvus 19530 冲突）。  
复用本机已在跑的 Milvus：`MILVUS_PORT=19530 uv run python step01_check_milvus.py`

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `step01_check_milvus.py` | 连 URI、读版本、列 collections |
| `demo_create_collection.py` | 简版 schema：`id` + `embedding`（384 dim） |
| `demo_crud.py` | insert / search / delete + flush |
| `demo_rag_search.py` | 完整 RAG 半链路；collection 含 `text` 字段 |

## 收工后清理

学完可执行（可重建）：

```bash
docker compose down
rm -rf .venv __pycache__
```
