"""Day24–25 Lesson 1 — 同步串行 vs 异步并发（假装 I/O：asyncio.sleep）。

不连真模型：只证明「干等」时 async 能交错等待。
"""

from __future__ import annotations

import asyncio
import time


def sync_call(name: str, delay: float) -> str:
    """同步：time.sleep 会堵死当前线程，别人插不进来。"""
    print(f"  [sync] {name} 开始等 {delay}s…")
    time.sleep(delay)
    print(f"  [sync] {name} 结束")
    return name


async def async_call(name: str, delay: float) -> str:
    """异步：await sleep 时把控制权交回事件循环，可去跑别的协程。"""
    print(f"  [async] {name} 开始等 {delay}s…")
    await asyncio.sleep(delay)
    print(f"  [async] {name} 结束")
    return name


def run_sync_serial() -> None:
    t0 = time.perf_counter()
    sync_call("A", 0.4)
    sync_call("B", 0.4)
    sync_call("C", 0.4)
    print(f"同步串行总耗时: {time.perf_counter() - t0:.2f}s  （约 0.4×3）\n")


async def run_async_concurrent() -> None:
    t0 = time.perf_counter()
    await asyncio.gather(
        async_call("A", 0.4),
        async_call("B", 0.4),
        async_call("C", 0.4),
    )
    print(f"异步并发总耗时: {time.perf_counter() - t0:.2f}s  （约 max(0.4)≈0.4）\n")


if __name__ == "__main__":
    print("=== 1) 同步串行（三次干等相加）===")
    run_sync_serial()
    print("=== 2) 异步并发（三次干等重叠）===")
    asyncio.run(run_async_concurrent())
