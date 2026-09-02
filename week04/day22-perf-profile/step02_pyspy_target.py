"""第 2 课：持续跑流水线，供 py-spy 从外部采样。

用法见 README / LEARN：另开终端对「本进程 PID」执行 py-spy。
也可：uv run py-spy record -o profile.svg -- uv run python step02_pyspy_target.py
"""

from __future__ import annotations

import os
import time

from workload import run_agent_pipeline


def main() -> None:
    print(f"PID={os.getpid()}")
    print("持续跑流水线中……另开终端用 py-spy 采样；Ctrl+C 结束。\n")
    i = 0
    while True:
        run_agent_pipeline(f"spy-{i}")
        i += 1
        if i % 2 == 0:
            print(f"  …已跑 {i} 次", flush=True)
        time.sleep(0.05)


if __name__ == "__main__":
    main()
