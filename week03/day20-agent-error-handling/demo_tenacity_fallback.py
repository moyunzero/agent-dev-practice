"""第 2 课：tenacity 重试 + 重试耗尽后降级。"""

from __future__ import annotations

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from flaky_price import CACHE_PRICE, fetch_price_flaky, get_call_count, reset_counter


@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(3),  # 最多 3 次尝试（含第一次）
    wait=wait_fixed(0.15),  # 教学用短等待；生产常用指数退避
    reraise=True,
)
def fetch_price_with_retry(sku: str) -> str:
    """带 tenacity 重试的查价。"""
    print(f"  …尝试调用 (已累计 {get_call_count() + 1} 次)")
    return fetch_price_flaky(sku, fail_times=2)


def fetch_price_resilient(sku: str) -> str:
    """重试 → 仍失败则降级到缓存价。"""
    try:
        return fetch_price_with_retry(sku)
    except (ConnectionError, RetryError) as e:
        cached = CACHE_PRICE.get(sku.upper())
        if cached is not None:
            return f"{sku.upper()} 暂不可用实时价，降级缓存价 {cached} 元（原因: {e}）"
        return f"{sku.upper()} 查询失败且无缓存，请稍后再试。（{e}）"


def main() -> None:
    print("=== A. fail_times=2，最多试 3 次 → 第 3 次应成功 ===\n")
    reset_counter()
    print("结果:", fetch_price_resilient("SKU-1"))
    print(f"实际调用次数: {get_call_count()}\n")

    print("=== B. fail_times 永远失败（改用会一直失败的包装）→ 降级 ===\n")

    @retry(
        retry=retry_if_exception_type(ConnectionError),
        stop=stop_after_attempt(2),
        wait=wait_fixed(0.05),
        reraise=True,
    )
    def always_fail(sku: str) -> str:
        raise ConnectionError("模拟服务彻底挂了")

    def with_fallback(sku: str) -> str:
        try:
            return always_fail(sku)
        except ConnectionError as e:
            cached = CACHE_PRICE.get(sku.upper())
            return f"{sku.upper()} 降级缓存价 {cached} 元（{e}）"

    print("结果:", with_fallback("SKU-2"))
    print("\n要点：retry 处理「偶发」；fallback 处理「实在不行也要给个答复」。")


if __name__ == "__main__":
    main()
