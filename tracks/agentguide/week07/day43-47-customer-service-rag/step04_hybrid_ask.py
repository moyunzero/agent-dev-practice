"""Lesson 4: 库精确 → FAQ 回退 → 需人工。"""

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

app = FastAPI(title="customer-service-rag-day43-47-l4")


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
        # 库无行 → 再试 FAQ（通常仍不够）→ 需人工
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

    # 无订单号/SKU：政策类走 FAQ
    return faq_or_human(q)
