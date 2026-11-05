"""Day24–25 Lesson 2 — 多路「API 干等」：串行 vs gather；以及 async 里误用 time.sleep。"""

from __future__ import annotations

import asyncio
import time


def call_api_sync(name: str) -> str:
    """假装一次同步 HTTP/模型调用（阻塞当前线程）。"""
    print(f"  sync-{name} …")
    time.sleep(0.35)
    return f"ok-{name}"


async def call_api_async(name: str) -> str:
    """假装一次异步 HTTP/模型调用（await 时让出事件循环）。"""
    print(f"  async-{name} …")
    await asyncio.sleep(0.35)
    return f"ok-{name}"


async def call_api_wrong(name: str) -> str:
    """错误示范：写在 async def 里，但仍用同步 sleep → 依然堵死循环。"""
    print(f"  WRONG-{name} …")
    time.sleep(0.35)  # 不要这么干
    return f"ok-{name}"


def demo_serial() -> None:
    t0 = time.perf_counter()
    results = [call_api_sync("A"), call_api_sync("B"), call_api_sync("C")]
    print(f"串行 3 次 API: {time.perf_counter() - t0:.2f}s → {results}\n")


async def demo_gather() -> None:
    t0 = time.perf_counter()
    results = await asyncio.gather(
        call_api_async("A"),
        call_api_async("B"),
        call_api_async("C"),
    )
    print(f"gather 并发 3 次: {time.perf_counter() - t0:.2f}s → {results}\n")


async def demo_wrong() -> None:
    t0 = time.perf_counter()
    results = await asyncio.gather(
        call_api_wrong("A"),
        call_api_wrong("B"),
        call_api_wrong("C"),
    )
    print(f"错误：async+time.sleep: {time.perf_counter() - t0:.2f}s → {results}")
    print("  （仍≈相加；函数是 async 没用，关键看 await 的是否真异步）\n")


if __name__ == "__main__":
    print("=== A) 同步串行 ===")
    demo_serial()
    print("=== B) asyncio.gather 并发 ===")
    asyncio.run(demo_gather())
    print("=== C) 坑：async def 里写 time.sleep ===")
    asyncio.run(demo_wrong())
