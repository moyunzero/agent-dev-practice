"""第 1 课：用标准库 cProfile 找 CPU 热点。"""

from __future__ import annotations

import cProfile
import pstats
from io import StringIO

from workload import run_agent_pipeline


def main() -> None:
    n = 3
    print(f"=== cProfile：连续跑 {n} 次 run_agent_pipeline ===\n")

    profiler = cProfile.Profile()
    profiler.enable()
    for i in range(n):
        out = run_agent_pipeline(f"nebula-q-{i}")
        print(f"  run[{i}] -> {out[:60]}…")
    profiler.disable()

    buf = StringIO()
    stats = pstats.Stats(profiler, stream=buf)
    stats.strip_dirs().sort_stats("tottime")
    stats.print_stats(12)

    print("\n--- 按 tottime（函数自身耗时）Top ---")
    print(buf.getvalue())
    print(
        "读表提示：\n"
        "- ncalls：调用次数\n"
        "- tottime：不含子调用的自身时间 ← 找 CPU 热点看这个\n"
        "- cumtime：含子集的累计时间\n"
        "期望：fake_retrieve（及 hashlib）的 tottime 很高 = CPU 热点；\n"
        "time.sleep 的 tottime 也高 = 在「等待」，不是算力打满。\n"
        "两者都是瓶颈，优化手段不同（减计算 vs 并发/缓存/更快推理）。"
    )


if __name__ == "__main__":
    main()
