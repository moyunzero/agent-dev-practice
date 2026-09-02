"""Day28 Lesson 4 — Locust 打「优化前」反例 /async-block。

先起 Day24–25：
  cd week04/day24-25-async && uv run uvicorn main_api:app --port 8024

再：
  uv run locust -f locustfile_async_block.py --host http://127.0.0.1:8024
Web UI 参数尽量与 Lesson 2 一致（如 10 users, spawn 2），跑同样时长后对比 RPS / 99%。
"""

from __future__ import annotations

from locust import HttpUser, between, task


class BlockUser(HttpUser):
    wait_time = between(0.1, 0.3)

    @task
    def hit_async_block(self) -> None:
        self.client.get("/async-block", params={"q": "load-test"})
