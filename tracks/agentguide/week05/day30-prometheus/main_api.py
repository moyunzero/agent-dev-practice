"""Day30 — FastAPI + Instrumentator + 自定义业务指标。

Instrumentator（HTTP 核心指标）：
- 请求次数 → QPS
- 耗时 Histogram → 延迟
- 状态码 → 错误率

自定义 Counter（对齐手撕：缓存命中）：
- cache_lookups_total{result="hit|miss"}

启动：
  uv sync
  uv run uvicorn main_api:app --port 8030

验证：
  curl -s 'http://127.0.0.1:8030/ask?q=hello'
  curl -s 'http://127.0.0.1:8030/ask?q=hello'   # 第二次应 hit
  curl -s http://127.0.0.1:8030/metrics | rg 'cache_lookups'
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="day30-prometheus")

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# 业务自定义：只增不减的 Counter；用 label 区分命中/未命中
CACHE_LOOKUPS = Counter(
    "cache_lookups_total",
    "Ask answer cache lookups",
    labelnames=("result",),
)

_ANSWER_CACHE: dict[str, str] = {}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    """带微型内存缓存；命中/未命中都会推自定义 Counter。"""
    if q in _ANSWER_CACHE:
        CACHE_LOOKUPS.labels(result="hit").inc()
        return {"q": q, "answer": _ANSWER_CACHE[q], "cache": "hit"}

    CACHE_LOOKUPS.labels(result="miss").inc()
    await asyncio.sleep(0.05)  # 模拟「算答案」耗时
    answer = f"echo:{q}"
    _ANSWER_CACHE[q] = answer
    return {"q": q, "answer": answer, "cache": "miss"}


@app.get("/fail")
async def fail() -> dict:
    """故意 500，方便观察错误相关指标。"""
    raise HTTPException(status_code=500, detail="boom")
