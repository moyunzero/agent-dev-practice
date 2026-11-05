"""Day48–51 Lesson 4 — 压测 POST /ask（复用 Day28 Locust 思路）。

前置：本目录 docker compose 已起（API :8048）

本机：
  uv sync
  uv run locust -f locustfile.py --host http://127.0.0.1:8048

无头模式（直接打出数字）：
  uv run locust -f locustfile.py --host http://127.0.0.1:8048 \
    --headless -u 50 -r 10 -t 30s
"""

from __future__ import annotations

from locust import HttpUser, between, task


class AskUser(HttpUser):
    wait_time = between(0.05, 0.15)

    @task
    def hit_ask(self) -> None:
        self.client.post(
            "/ask",
            json={"q": "订单 ORD-1001 到哪了？"},
            name="/ask",
        )
