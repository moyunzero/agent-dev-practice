"""Day32 — 待打包的 FastAPI（与 Day30 同构，含 /metrics）。"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="day32-docker")

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

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
    if q in _ANSWER_CACHE:
        CACHE_LOOKUPS.labels(result="hit").inc()
        return {"q": q, "answer": _ANSWER_CACHE[q], "cache": "hit"}

    CACHE_LOOKUPS.labels(result="miss").inc()
    await asyncio.sleep(0.05)
    answer = f"echo:{q}"
    _ANSWER_CACHE[q] = answer
    return {"q": q, "answer": answer, "cache": "miss"}


@app.get("/fail")
async def fail() -> dict:
    raise HTTPException(status_code=500, detail="boom")
