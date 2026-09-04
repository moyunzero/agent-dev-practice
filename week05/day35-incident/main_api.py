"""Day35 Lesson 2 — 可注入故障的最小 FastAPI（JSON 请求日志）。

启动示例：
  FAULT=off   uv run uvicorn main_api:app --port 8035
  FAULT=slow  uv run uvicorn main_api:app --port 8035
  FAULT=error uv run uvicorn main_api:app --port 8035

验证：
  curl -s -w '\\nHTTP %{http_code} time=%{time_total}\\n' 'http://127.0.0.1:8035/ask?q=demo'
  # 看 uvicorn 终端：一行 JSON（event=request_done，含 fault / status / duration_ms）
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# off | slow | error — 改环境变量后需重启进程
FAULT = os.getenv("FAULT", "off").strip().lower()
SLOW_SECONDS = float(os.getenv("SLOW_SECONDS", "2.0"))

app = FastAPI(title="day35-incident")


def configure_json_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


configure_json_logging()
log = structlog.get_logger()


class RequestJsonLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status = response.status_code if response is not None else 500
            log.info(
                "request_done",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=duration_ms,
                fault=FAULT,
                q=request.query_params.get("q"),
            )


app.add_middleware(RequestJsonLogMiddleware)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "fault": FAULT}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    if FAULT == "slow":
        await asyncio.sleep(SLOW_SECONDS)
        return {"q": q, "answer": f"echo:{q}", "fault": FAULT}
    if FAULT == "error":
        raise HTTPException(status_code=500, detail="injected fault: downstream boom")
    return {"q": q, "answer": f"echo:{q}", "fault": FAULT}
