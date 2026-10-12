# 电商智能客服：先查 PostgreSQL，再 FAQ 回退

纯文档 RAG 很容易把「订单到哪了」答成一段物流常识——听着像那么回事，却不是这一单的事实。  
电商客服要的是：**能进表的先精确查表；政策说明再搜帮助文档；两边都没有就别硬答。**

本文按学习路线「项目一 · 智能客服 RAG」的 **需求分析 → 架构 → 核心功能** 做一版最小可跑系统：FastAPI + PostgreSQL + FAQ 文档回退。性能压测、完整监控、整栈 Compose 部署属于后续「优化与部署」阶段，文末边界写清，避免漏项。

## 你将会得到什么

1. 分清事务状态类 / 政策说明类 / 需人工  
2. 画出「先库后 FAQ」数据流，并实现统一 `POST /ask`  
3. 用 Docker 起 Postgres，用参数化 SQL 查订单与商品  
4. 库未命中时回退 FAQ；不够置信则 `need_human`  
5. 知道整项目还缺哪些（压测 / 监控 / 整栈部署），下一步去哪补  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### 智能客服 / 重复性问题

| 层 | 说明 |
|----|------|
| **是什么** | 用程序自动回答大量雷同咨询（订单进度、退货规则等），把人工留给例外 |
| **在本文干什么** | 演示三类问句能否走到正确路径，而不是追求「自动率 80%」这个数字 |
| **怎么区分** | 「能答」≠「敢编」。没有库行、没有可靠文档时，应标需人工 |

### PostgreSQL 精确查询

| 层 | 说明 |
|----|------|
| **是什么** | 关系库用主键/条件查出**确定的一行**（如 `order_id = ORD-1001`） |
| **在本文干什么** | 订单状态、物流单号、SKU 库存都从库读 |
| **怎么区分** | 精确查 ≠ 向量相似搜。订单号乱写时库应返回空，不能「找个差不多的单」 |

### FAQ 文档模糊检索

| 层 | 说明 |
|----|------|
| **是什么** | 从帮助文档里找与问句相关的段落 |
| **在本文干什么** | 退货天数、包邮规则等；库走不通或没有订单号时才进这里 |
| **怎么区分** | 本文用「字 bigram + 关键词加分」做最小模糊匹配，便于看清路由。生产上常换成向量库 / BM25+向量混合检索，**路由不变** |

### 混合路径（本文的「混合」）

| 层 | 说明 |
|----|------|
| **是什么** | 两种数据源按优先级协作：结构化库 + 非结构化文档 |
| **在本文干什么** | 先库后 FAQ，不是「向量和 BM25 同时召回再融合」那种 Hybrid Search |
| **怎么区分** | Week2 的 Hybrid（BM25+向量）是**同层检索融合**；本项目是**跨源路由**。名字都叫混合，别混 |

### FastAPI `POST /ask`

| 层 | 说明 |
|----|------|
| **是什么** | HTTP 接口：收 JSON 问句，返回答案与来源 |
| **在本文干什么** | 唯一入口；内部决定走库、走 FAQ 还是需人工 |
| **怎么区分** | 浏览器打开根路径 `/` 会 404；必须 **POST** 到 `/ask` |

### `source` 与 `need_human`

| 层 | 说明 |
|----|------|
| **是什么** | 回答从哪来、要不要转人工 |
| **在本文干什么** | `db` / `faq` / `none`；FAQ 答案可加前缀「帮助中心」以免和库事实混淆 |
| **怎么区分** | `source=db` 是表事实；`source=faq` 是政策摘录；不要给库答案也贴「帮助中心」 |

### Docker Compose 里的 Postgres

| 层 | 说明 |
|----|------|
| **是什么** | 用容器起数据库；本文映射到宿主机 `5433` 端口 |
| **在本文干什么** | 存订单与商品种子数据；改 `seed.sql` 后需 `down -v` 才会重跑初始化 |
| **怎么区分** | 本文 Compose **只起库**；API 仍本机 `uvicorn`。整栈（API+库一起 compose）留到优化部署阶段 |

```text
用户问句
   → POST /ask
   → 抽出 ORD-* / SKU-* ？
        是 → PostgreSQL 有行？──是──► source=db
              └─否──► FAQ ──够分──► source=faq
                       └─不够──► need_human
        否 → FAQ（同上）
```

---

## 需求分析（三类问句）

| 类型 | 例子 | 答案在哪 |
|------|------|----------|
| 事务/状态 | 订单到哪了？某 SKU 库存？ | PostgreSQL |
| 政策/说明 | 7 天能退吗？满多少包邮？ | FAQ |
| 越界 | 要赔偿 200 元 | 需人工 |

口诀：**能进表的先查表；写在说明书里的再搜文档。**

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（起 Postgres）  

空目录结构：

```text
customer-service-rag/
├── docker-compose.yml
├── pyproject.toml
├── data/seed.sql
├── faq/return.md
├── faq/shipping.md
├── faq_search.py
└── step04_hybrid_ask.py
```

---

## 完整文件

### `pyproject.toml`

```toml
[project]
name = "day43-47-customer-service-rag"
version = "0.1.0"
description = "ecommerce customer-service: DB first, FAQ fallback"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.141.1",
    "psycopg[binary]>=3.2.0",
    "uvicorn[standard]>=0.52.4",
]
```

### `docker-compose.yml`

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: cs
      POSTGRES_PASSWORD: cs
      POSTGRES_DB: customer_service
    ports:
      - "5433:5432"
    volumes:
      - ./data/seed.sql:/docker-entrypoint-initdb.d/01-seed.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U cs -d customer_service"]
      interval: 2s
      timeout: 5s
      retries: 15
```

### `data/seed.sql`

```sql
CREATE TABLE IF NOT EXISTS orders (
    order_id    TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    tracking_no TEXT
);

CREATE TABLE IF NOT EXISTS products (
    sku   TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    color TEXT,
    stock INT NOT NULL DEFAULT 0
);

INSERT INTO orders (order_id, user_id, status, tracking_no) VALUES
    ('ORD-1001', 'u_demo', 'shipped', 'SF123'),
    ('ORD-1002', 'u_demo', 'delivered', 'YT999'),
    ('ORD-1003', 'u_demo', 'processing', 'ZT777')
ON CONFLICT DO NOTHING;

INSERT INTO products (sku, name, color, stock) VALUES
    ('SKU-88', 'Demo Tee', 'red', 12),
    ('SKU-99', 'Demo Cap', 'black', 0)
ON CONFLICT DO NOTHING;
```

### `faq/return.md`

```markdown
# 退货政策

自签收起 7 天内可无理由退货。

商品须不影响二次销售；缺原包装可能影响退款。

运费：质量问题商家承担；个人原因默认买家承担（以活动页为准）。
```

### `faq/shipping.md`

```markdown
# 包邮与运费

满 99 元包邮；偏远地区以结算页为准。

一般订单支付后 48 小时内发货。

物流时效仅供参考，以承运商轨迹为准。
```

### `faq_search.py`

```python
"""FAQ 模糊检索（规范化 + bigram；关键词加分）。"""

from __future__ import annotations

import re
from pathlib import Path

FAQ_DIR = Path(__file__).resolve().parent / "faq"
MIN_SCORE = 0.2
BOOST_KEYWORDS = ("退货", "退款", "7天", "无理由", "包邮", "运费", "发货")


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    s = s.replace("七天", "7天")
    return s


def _bigram_score(query: str, text: str) -> float:
    q = _norm(query)
    t = _norm(text)
    if len(q) < 2:
        return 1.0 if q and q in t else 0.0
    hits = 0
    total = 0
    for i in range(len(q) - 1):
        bg = q[i : i + 2]
        total += 1
        if bg in t:
            hits += 1
    return hits / total if total else 0.0


def load_chunks() -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for path in sorted(FAQ_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8").strip()
        for block in raw.split("\n\n"):
            block = block.strip()
            if block and not block.startswith("#"):
                chunks.append({"doc_id": path.name, "text": block})
    return chunks


def search_faq(query: str, *, min_score: float = MIN_SCORE) -> dict | None:
    qn = _norm(query)
    best: dict | None = None
    best_score = -1.0
    for chunk in load_chunks():
        score = _bigram_score(query, chunk["text"])
        tn = _norm(chunk["text"])
        for kw in BOOST_KEYWORDS:
            if kw in qn and kw in tn:
                score = max(score, 0.55)
        if score > best_score:
            best_score = score
            best = {**chunk, "score": round(score, 4)}
    if best is None or best_score < min_score:
        return None
    return best
```

### `step04_hybrid_ask.py`

```python
from __future__ import annotations

import os
import re
from typing import Any

import psycopg
from fastapi import FastAPI
from pydantic import BaseModel, Field

from faq_search import search_faq

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://cs:cs@127.0.0.1:5433/customer_service",
)

ORDER_RE = re.compile(r"\bORD-\d+\b", re.IGNORECASE)
SKU_RE = re.compile(r"\bSKU-\d+\b", re.IGNORECASE)

app = FastAPI(title="customer-service-rag")


class AskRequest(BaseModel):
    q: str = Field(..., min_length=1)
    user_id: str = "u_demo"


class AskResponse(BaseModel):
    answer: str
    source: str
    refs: dict[str, Any] | None
    need_human: bool


def lookup_order(order_id: str) -> dict[str, Any] | None:
    oid = order_id.upper()
    with psycopg.connect(DSN) as conn:
        row = conn.execute(
            "SELECT order_id, status, tracking_no FROM orders WHERE order_id = %s",
            (oid,),
        ).fetchone()
    if row is None:
        return None
    return {"order_id": row[0], "status": row[1], "tracking_no": row[2]}


def lookup_product(sku: str) -> dict[str, Any] | None:
    key = sku.upper()
    with psycopg.connect(DSN) as conn:
        row = conn.execute(
            "SELECT sku, name, color, stock FROM products WHERE sku = %s",
            (key,),
        ).fetchone()
    if row is None:
        return None
    return {"sku": row[0], "name": row[1], "color": row[2], "stock": row[3]}


def faq_or_human(q: str) -> AskResponse:
    hit = search_faq(q)
    if hit:
        return AskResponse(
            answer=f"【帮助中心】{hit['text']}",
            source="faq",
            refs={"doc_id": hit["doc_id"], "score": hit["score"]},
            need_human=False,
        )
    return AskResponse(
        answer="这个问题需要人工客服协助处理。",
        source="none",
        refs=None,
        need_human=True,
    )


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    q = body.q.strip()

    order_m = ORDER_RE.search(q)
    if order_m:
        hit = lookup_order(order_m.group(0))
        if hit:
            return AskResponse(
                answer=(
                    f"订单 {hit['order_id']} 当前状态：{hit['status']}，"
                    f"物流单号 {hit['tracking_no']}。"
                ),
                source="db",
                refs=hit,
                need_human=False,
            )
        return faq_or_human(q)

    sku_m = SKU_RE.search(q)
    if sku_m:
        hit = lookup_product(sku_m.group(0))
        if hit:
            return AskResponse(
                answer=(
                    f"{hit['sku']}（{hit['name']}）颜色 {hit['color']}，"
                    f"库存 {hit['stock']}。"
                ),
                source="db",
                refs=hit,
                need_human=False,
            )
        return faq_or_human(q)

    return faq_or_human(q)
```

**API 要点（psycopg）**：`connect(DSN)` 连库；`execute(sql, (param,))` 参数绑定，禁止把用户输入拼进 SQL 字符串；`fetchone()` 无行返回 `None`。详见 [Psycopg 3 文档](https://www.psycopg.org/psycopg3/docs/basic/usage.html)。

---

## 启动与验证

```bash
docker compose up -d
# 等 healthy（刚 up 立刻 curl 可能 Connection refused → 500）
uv sync
uv run uvicorn step04_hybrid_ask:app --host 127.0.0.1 --port 8043
```

```bash
# 库命中
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？","user_id":"u_demo"}'

# FAQ 命中
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"买错了，7 天内能退吗？"}'

# 需人工
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"这次晚到要赔我 200 块"}'
```

**期望**：

| 问句 | `source` | 其它 |
|------|----------|------|
| ORD-1001 | `db` | shipped / SF123，`need_human=false` |
| 7 天能退 | `faq` | 含「7 天」，可有「【帮助中心】」前缀 |
| 赔 200 | `none` | `need_human=true` |

改种子数据后重建库：

```bash
docker compose down -v && docker compose up -d
```

`-v` 会删卷；否则 init SQL 不会重跑。

---

## 新手向坑

| 现象 | 原因 | 处理 |
|------|------|------|
| `{"detail":"Not Found"}` | 浏览器打开了 `/`，或没用 POST | 必须 `POST /ask` |
| `Internal Server Error` 刚 compose 后 | Postgres 尚未 ready | 等几秒或看 `docker compose ps` 的 healthy |
| 改了 `seed.sql` 库存不变 | 旧数据卷还在 | `down -v` 再 `up` |
| 库无行的订单直接人工、从没进 FAQ | 跑的是只含库逻辑的旧脚本 | 确认启动的是带 `faq_or_human` 的入口 |

---

## 边界：做了什么 / 故意没做什么

| 本文已做（对应路线 Day43–47：需求/架构/核心） | 未做（对应路线 Day48–51，**不得当作已完成**） |
|-----------------------------------------------|--------------------------------------------------|
| 需求分析三类问句 | QPS > 200、P99 < 500ms 压测达标 |
| 先库后 FAQ 架构与统一 API | LangSmith + Prometheus + Grafana 完整监控 |
| FAQ 文档 + PostgreSQL 订单/商品 | **整栈** Docker Compose（API+库一起部署）与项目文档 |
| 库精确 + FAQ 回退 + 需人工可演示 | FAQ 升级为生产级向量/混合检索 + LLM 生成（可选加深） |

对照上游「项目一」技术要求全文：核心路由已落地；性能、监控、整栈部署仍欠，须在后续天数补齐，不能漏。

---

## 收束

客服系统的第一刀不是「再堆一个向量库」，而是：**哪类问题必须查事实表，哪类才查说明书。**  
`POST /ask` 能稳定走出 `db` / `faq` / `need_human` 三条路，核心功能才算站住；再谈压得动、看得见、部署得起。
