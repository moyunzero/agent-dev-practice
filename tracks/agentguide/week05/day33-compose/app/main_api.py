"""Day33 — Compose 栈内 FastAPI：通过服务名连 Redis。"""

from __future__ import annotations

import asyncio
import os

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="day33-compose")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

CACHE_LOOKUPS = Counter(
    "cache_lookups_total",
    "Ask answer cache lookups",
    labelnames=("result",),
)

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")


def _redis():
    import redis

    return redis.Redis.from_url(REDIS_URL, decode_responses=True)


@app.get("/health")
async def health() -> dict:
    try:
        r = _redis()
        r.ping()
        redis_ok = True
    except Exception as e:  # noqa: BLE001 — 教学：健康检查要可读
        redis_ok = False
        return {"status": "degraded", "redis": False, "error": str(e)}
    return {"status": "ok", "redis": redis_ok}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    r = _redis()
    key = f"ask:{q}"
    cached = r.get(key)
    if cached is not None:
        CACHE_LOOKUPS.labels(result="hit").inc()
        return {"q": q, "answer": cached, "cache": "hit"}

    CACHE_LOOKUPS.labels(result="miss").inc()
    await asyncio.sleep(0.05)
    answer = f"echo:{q}"
    r.set(key, answer)
    return {"q": q, "answer": answer, "cache": "miss"}


@app.get("/fail")
async def fail() -> dict:
    raise HTTPException(status_code=500, detail="boom")
