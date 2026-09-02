"""对真实 Agent 进程做 py-spy：打印 PID，循环跑若干轮。"""

from __future__ import annotations

import os
import time

from real_agent import run_agent

Q = "单词 spy 有几个字母？把结果加1"


def main() -> None:
    print(f"PID={os.getpid()}")
    print("循环跑真实 Agent。另开终端（把数字换成上面的 PID，不要写尖括号）：")
    print(f"  uv run py-spy top --pid {os.getpid()}")
    print("或：uv run py-spy record -o agent_profile.svg --pid", os.getpid())
    print("Ctrl+C 结束。\n")
    i = 0
    while True:
        ans = run_agent(f"{Q} (round {i})")
        print(f"[{i}] {ans[:80]}", flush=True)
        i += 1
        time.sleep(0.2)


if __name__ == "__main__":
    main()
