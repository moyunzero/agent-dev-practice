"""Day34 Lesson 3 — FastAPI 请求打 JSON 结构化日志。

启动：
  uv sync
  uv run uvicorn main_api:app --port 8034

验证（另开终端）：
  curl -s 'http://127.0.0.1:8034/ask?q=hello'
  # 看跑 uvicorn 的终端：应出现一行 JSON（event=request_done）
"""

from __future__ import annotations

import logging
import sys
import time
import uuid

import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(title="day34-logging")


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
                q=request.query_params.get("q"),
            )


app.add_middleware(RequestJsonLogMiddleware)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    return {"q": q, "answer": f"echo:{q}"}
