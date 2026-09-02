"""回炉课：对真实 Agent（create_agent + Ollama）跑 cProfile。"""

from __future__ import annotations

import cProfile
import pstats
from io import StringIO

from real_agent import run_agent

DEFAULT_Q = "单词 agent 有几个字母？把结果加10"


def main() -> None:
    q = DEFAULT_Q
    print("=== cProfile × 真实 Agent（Day15 同构）===\n")
    print(f"Q: {q}\n")
    print(
        "先听原理再读表：\n"
        "- 墙钟时间多半花在「等 Ollama」→ 报表里常见 httpx/socket/等待相关\n"
        "- 本地工具 get_word_length / add 通常极快，tottime 很小\n"
        "- 这和玩具流水线不同：真 Agent 瓶颈常是「等待模型」，不是哈希 CPU\n"
    )

    profiler = cProfile.Profile()
    profiler.enable()
    answer = run_agent(q)
    profiler.disable()

    print(f"Answer: {answer}\n")

    buf = StringIO()
    stats = pstats.Stats(profiler, stream=buf)
    stats.strip_dirs().sort_stats("cumtime")
    stats.print_stats(20)
    print("--- 按 cumtime Top20（看整条调用链谁拖时间）---")
    print(buf.getvalue())

    buf2 = StringIO()
    stats2 = pstats.Stats(profiler, stream=buf2)
    stats2.strip_dirs().sort_stats("tottime")
    stats2.print_stats(15)
    print("--- 按 tottime Top15（看谁自己在忙）---")
    print(buf2.getvalue())
    print(
        "观察任务：\n"
        "1) Answer 是否合理（工具被调用）\n"
        "2) cumtime 靠前的是不是网络/等待相关\n"
        "3) get_word_length / add 是否几乎看不到（说明工具本身不是瓶颈）"
    )


if __name__ == "__main__":
    main()
