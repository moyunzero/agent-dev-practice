"""并发打 /async-ask 与 /async-block，对比墙钟。"""

from __future__ import annotations

import concurrent.futures
import time

import httpx

BASE = "http://127.0.0.1:8024"
N = 3


def bench(path: str) -> float:
    urls = [f"{BASE}{path}?q={i}" for i in range(N)]
    t0 = time.perf_counter()
    with httpx.Client(timeout=30.0) as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as pool:
            list(pool.map(lambda u: client.get(u).raise_for_status(), urls))
    return time.perf_counter() - t0


if __name__ == "__main__":
    httpx.get(f"{BASE}/health", timeout=5.0).raise_for_status()

    t_ok = bench("/async-ask")
    t_bad = bench("/async-block")
    print(f"并发 {N} × /async-ask   (await) : {t_ok:.2f}s  ← 期望约 0.4")
    print(f"并发 {N} × /async-block (sleep) : {t_bad:.2f}s  ← 期望约 1.2（堵 loop）")
    print("对照读代码：/sync-ask 是改造前的 def；生产 I/O 应改成 /async-ask 这种写法。")
