"""Day24–25 Lesson 3 — FastAPI 异步改造。

要点：
- 手撕形态：同步 I/O（time.sleep / 同步 HTTP）→ async def + await 真异步
- 注意：uvicorn 对「普通 def」会丢进线程池，并发时也可能重叠；
  更致命的是 async def 里写阻塞，会堵死整个事件循环。

启动：
  uv run uvicorn main_api:app --port 8024

另开终端：
  uv run python step03_bench_client.py
"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI

app = FastAPI(title="day24-25-async")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# --- 改造前（示意）：同步路由 + 阻塞 I/O ---
@app.get("/sync-ask")
def sync_ask(q: str = "hi") -> dict:
    time.sleep(0.4)
    return {"mode": "sync-def", "q": q, "answer": f"echo:{q}"}


# --- 改造后：异步路由 + await ---
@app.get("/async-ask")
async def async_ask(q: str = "hi") -> dict:
    await asyncio.sleep(0.4)
    return {"mode": "async-await", "q": q, "answer": f"echo:{q}"}


# --- 反例：挂了 async 却阻塞事件循环 ---
@app.get("/async-block")
async def async_block(q: str = "hi") -> dict:
    time.sleep(0.4)  # 错误：堵死 loop，并发请求会串行
    return {"mode": "async-block", "q": q, "answer": f"echo:{q}"}
