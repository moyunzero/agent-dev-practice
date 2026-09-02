"""Day28 Lesson 2 — Locust 最小压测脚本。

被测服务（另开终端，来自 Day24–25）：
  cd week04/day24-25-async && uv sync && uv run uvicorn main_api:app --port 8024

本目录启动 Locust：
  uv sync
  uv run locust -f locustfile_async_ask.py --host http://127.0.0.1:8024

浏览器打开 http://127.0.0.1:8089 ，设用户数与启动速率后 Start。
"""

from __future__ import annotations

from locust import HttpUser, between, task


class AskUser(HttpUser):
    """模拟一个「不停打 /async-ask」的虚拟用户。"""

    # 每个任务之间随机休息 0.1～0.3 秒（模拟思考间隔；压测时可改小）
    wait_time = between(0.1, 0.3)

    @task
    def hit_async_ask(self) -> None:
        # self.client 是带统计的 HTTP 客户端；失败会记进失败率
        self.client.get("/async-ask", params={"q": "load-test"})
