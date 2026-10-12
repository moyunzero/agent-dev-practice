# Day43–47 Lesson 3 — 核心·库查（先读再跑）

> 挂钩上游：**核心功能开发** 里的「优先从数据库精确查询」  
> 脚本：`step03_db_ask.py` · 库：`docker compose` 起的 PostgreSQL

## 原理（一个点）

订单 / SKU 是**表里的一行事实**。流程：

1. 从问句里用正则抽出 `ORD-1001` / `SKU-88`  
2. `SELECT ... WHERE order_id = %s`（参数绑定，不拼 SQL）  
3. 有行 → `source=db` 返回答案；无行 → 本课先 `need_human`（Lesson 4 再接 FAQ）

## 带读主路径（`step03_db_ask.py`）

| 位置 | 干什么 |
|------|--------|
| `DSN` / `DATABASE_URL` | 连 `127.0.0.1:5433`（compose 映射，避免和本机 5432 撞车） |
| `lookup_order` | `psycopg.connect` → `execute(..., (oid,))` → `fetchone` |
| `ask` | 先匹配订单号，再匹配 SKU；都没有 → 说明本课边界 |

API 细节见 `lesson_api_cheatsheet.md`。

## 启动

```bash
cd week07/day43-47-customer-service-rag
docker compose up -d
uv sync
uv run uvicorn step03_db_ask:app --port 8043
```

另开终端验收：

```bash
curl -s http://127.0.0.1:8043/ask \
  -H 'content-type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？","user_id":"u_demo"}'
```

**期望**：`source` 为 `"db"`，答案含 `shipped` / `SF123`。

## 本课动手（先预测再改）

种子里已有 `ORD-1002`（`delivered` / `YT999`）。

1. **先说**：把 curl 里的订单改成 `ORD-1002`，响应里 `status` / 物流单号应是什么？  
2. **再跑**验证  
3. **小改动**：在 `data/seed.sql` 增加一单 `ORD-1003`（自定 status/tracking），`docker compose down -v && docker compose up -d` 重建库后，用 curl 问这一单，确认 `source=db`

（改 seed 后必须 `-v` 清卷，否则 init SQL 不会重跑。）
