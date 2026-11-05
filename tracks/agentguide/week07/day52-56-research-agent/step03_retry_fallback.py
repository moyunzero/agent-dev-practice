"""Day52–56 Lesson 5 — 工具重试 + 降级（复用 Day20 思路）。

人话：偶发失败多试几次；试尽了就返回 fixture，不把整条流水线砸死。

运行：
  uv run python step03_retry_fallback.py
"""

from __future__ import annotations

import os

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

# 前 N 次抛错，之后成功（模拟网络抖动）
_FAIL_LEFT = int(os.getenv("FLAKY_FAIL_TIMES", "2"))
_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "3"))


def _flaky_live_search(query: str) -> str:
    global _FAIL_LEFT
    if _FAIL_LEFT > 0:
        _FAIL_LEFT -= 1
        raise ConnectionError(f"模拟搜索抖动（还剩将失败次数由环境控制）: {query!r}")
    return f"[live] 搜索成功: {query}"


def _fixture_search(query: str) -> str:
    return (
        f"[fixture 降级] query={query!r}\n"
        "1. Acme 工业传感器扩产 — 来源: https://example.com/acme-expand\n"
        "2. Acme FY2024 营收摘要 — 来源: https://example.com/acme-fy2024"
    )


@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(_ATTEMPTS),
    wait=wait_fixed(0.1),
    reraise=True,
)
def _search_with_retry(query: str) -> str:
    print(f"  …尝试 live 搜索 (RETRY_ATTEMPTS={_ATTEMPTS})")
    return _flaky_live_search(query)


def web_search_resilient(query: str) -> str:
    """重试 → 耗尽则降级 fixture。挂进 Agent 前可包一层同样逻辑。"""
    try:
        return _search_with_retry(query)
    except ConnectionError as e:
        print(f"  重试耗尽，降级 fixture（{e}）")
        return _fixture_search(query)


def main() -> None:
    global _FAIL_LEFT
    _FAIL_LEFT = int(os.getenv("FLAKY_FAIL_TIMES", "2"))
    print(f"=== A. 失败 {_FAIL_LEFT} 次，最多试 {_ATTEMPTS} 次 → 应 live 成功 ===\n")
    print("结果:", web_search_resilient("Acme Corp news"))

    print("\n=== B. 失败 5 次、最多试 2 次 → 应降级 fixture ===\n")
    os.environ["FLAKY_FAIL_TIMES"] = "5"
    # 重新绑定：用局部更小 attempts 演示降级
    from tenacity import RetryError

    fail_left = 5

    @retry(
        retry=retry_if_exception_type(ConnectionError),
        stop=stop_after_attempt(2),
        wait=wait_fixed(0.05),
        reraise=True,
    )
    def always_jitter(query: str) -> str:
        nonlocal fail_left
        if fail_left > 0:
            fail_left -= 1
            raise ConnectionError("一直抖")
        return "[live] ok"

    try:
        print("结果:", always_jitter("Acme"))
    except (ConnectionError, RetryError) as e:
        print("结果:", _fixture_search("Acme"), f"\n  （原因: {e}）")

    print("\n要点：retry 扛偶发；fallback 保证仍有可审计文本。")


if __name__ == "__main__":
    main()
