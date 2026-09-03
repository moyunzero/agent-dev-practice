"""Day34 Lesson 2 — structlog 输出一行一条 JSON。

运行：
  uv sync
  uv run python step02_json_logger.py
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_json_logging() -> None:
    """把标准 logging + structlog 都打成 JSON 到 stdout。"""
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


def main() -> None:
    configure_json_logging()
    log = structlog.get_logger()
    log.info(
        "request_done",
        path="/ask",
        method="GET",
        status=200,
        duration_ms=52,
        q="hello",
    )
    log.warning("cache_miss", path="/ask", q="hello")


if __name__ == "__main__":
    main()
