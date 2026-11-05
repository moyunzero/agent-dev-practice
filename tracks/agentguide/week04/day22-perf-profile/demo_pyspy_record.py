"""尝试用 py-spy record 生成火焰图 SVG。"""

from __future__ import annotations

import subprocess
from pathlib import Path

OUT = Path(__file__).parent / "profile.svg"
TARGET = (
    "from workload import run_agent_pipeline\n"
    "for i in range(8):\n"
    "    run_agent_pipeline(f'x{i}')\n"
)


def main() -> None:
    cmd = [
        "uv",
        "run",
        "py-spy",
        "record",
        "-o",
        str(OUT),
        "--",
        "uv",
        "run",
        "python",
        "-c",
        TARGET,
    ]
    print("运行:", " ".join(cmd[:8]), "…")
    code = subprocess.call(cmd)
    if code == 0 and OUT.exists():
        print(f"已生成火焰图: {OUT}")
        return
    print(
        "py-spy 未成功（常见：macOS 权限）。\n"
        "可改用：\n"
        "  uv run python step02_pyspy_target.py   # 看 PID\n"
        "  uv run py-spy top --pid <PID>\n"
        "第 1 课 cProfile 已能定位 CPU 热点，本课重点是「知道 py-spy 怎么用」。"
    )


if __name__ == "__main__":
    main()
