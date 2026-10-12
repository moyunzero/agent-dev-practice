# Week 7 / Day 43–47 — 项目一：智能客服 RAG（核心）

> **状态**：`available`  
> **前置**：Week1–6 基础（FastAPI / RAG 概念）  
> **长文教程**（可选）：[电商智能客服：先查 PostgreSQL，再 FAQ 回退](../../notes/week07/day43-47-customer-service-rag.md)

## 今日目标

完成需求分析、架构设计、核心功能开发（库精确查 → FAQ 回退 → 需人工）。

## 前置

- Docker（PostgreSQL）  
- Python 3.12+、uv  

## 文件说明

| 文件 | 作用 |
|------|------|
| `lesson01_requirements.md` | 需求分析 |
| `lesson02_architecture.md` | 架构：先库后 FAQ |
| `lesson03_db.md` / `step03_db_ask.py` | 仅库精确（对照用） |
| `lesson04_faq.md` / `faq_search.py` / `faq/` | FAQ 回退 |
| `lesson05_e2e.md` / `step04_hybrid_ask.py` | 统一入口（验收用这个） |
| `lesson06_mastery.md` | 掌握检查 |
| `data/seed.sql` | 订单/商品种子 |
| `docker-compose.yml` | Postgres 16（宿主机 5433） |
| `lesson_api_cheatsheet.md` | psycopg /ask |
| `pyproject.toml` / `uv.lock` | FastAPI + psycopg |

## 推荐顺序

| 步骤 | 动作 |
|:----:|------|
| 1–2 | 读 lesson01 / lesson02 |
| 3 | `docker compose up -d` → 可选跑 step03 |
| 4–5 | 跑 **step04**，验收 db / faq / need_human |
| 6 | 掌握检查（见长文或 lesson06） |

## 验收命令

```bash
cd week07/day43-47-customer-service-rag
docker compose up -d
uv sync
uv run uvicorn step04_hybrid_ask:app --host 127.0.0.1 --port 8043
```

```bash
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？","user_id":"u_demo"}'
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"买错了，7 天内能退吗？"}'
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"这次晚到要赔我 200 块"}'
```

**期望**：依次 `source=db`、`source=faq`、`need_human=true`。

性能压测、完整监控、API+库整栈 Compose 见 Day48–51。
