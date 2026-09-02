"""第 1 课：无重试 —— 偶发失败直接炸。"""

from __future__ import annotations

from flaky_price import fetch_price_flaky, reset_counter


def main() -> None:
    reset_counter()
    print("=== 无重试：工具一失败，调用方直接收到异常 ===\n")
    try:
        print(fetch_price_flaky("SKU-1", fail_times=2))
    except ConnectionError as e:
        print(f"捕获异常: {e}")
        print("结果：用户看不到价格；Agent 若未处理，整轮可能中断。")
    print("\n要点：瞬时网络错误很常见 → 需要「再试几次」而不是一次放弃。")


if __name__ == "__main__":
    main()
