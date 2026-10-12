# Day43–47 Lesson 4 — 核心·FAQ 回退（先读再跑）

> 挂钩上游：无法命中数据库时，再从文档模糊检索  
> 新文件：`faq/*.md` · `faq_search.py` · `step04_hybrid_ask.py`  
> Lesson 3 的 `step03_db_ask.py` 保留对照，本课请跑 **step04**。

## 原理（一个点）

```text
有 ORD/SKU 且库有行 → source=db
否则 → search_faq(问句)
         分数够 → source=faq
         不够 → need_human
```

本课 FAQ 用「字 bigram 重叠」打分（实现短、好跟读）。  
和 Day4 Chroma **槽位相同**：都是「问句 → 文档片段」；以后可换成向量检索，**路由不变**。

## 带读（只盯新增）

| 文件 | 看什么 |
|------|--------|
| `faq/return.md` 等 | 政策写在文档里，不在订单表 |
| `faq_search.search_faq` | 扫所有片段打分；`< MIN_SCORE` 返回 `None` |
| `step04` 的 `faq_or_human` | FAQ 命中 / 需人工 |
| `ask` 里库无行的分支 | 不再直接 `need_human`，先 `return faq_or_human(q)` |

## 启动（换 step04，端口可仍用 8043）

先停掉旧的 uvicorn（Ctrl+C），再：

```bash
cd week07/day43-47-customer-service-rag
# Postgres 若已在跑可跳过
docker compose up -d
uv run uvicorn step04_hybrid_ask:app --host 127.0.0.1 --port 8043
```

## 验收

```bash
# 仍走库
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？"}'

# 走 FAQ（无订单号）
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"买错了，7 天内能退吗？"}'

# 越界 → 需人工
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"这次晚到要赔我 200 块"}'
```

**期望**：1)`source=db` 2)`source=faq` 且提到 7 天 3)`need_human=true`
