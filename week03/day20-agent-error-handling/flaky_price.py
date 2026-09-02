"""模拟不稳定的查价「API」：前几次抛错，之后成功。"""

from __future__ import annotations

# 全局计数：每次调用 +1（教学用，进程内有效）
_CALL_COUNT = 0

# 降级用的本地缓存价
CACHE_PRICE = {"SKU-1": 99.0, "SKU-2": 49.0}


def reset_counter() -> None:
    global _CALL_COUNT
    _CALL_COUNT = 0


def get_call_count() -> int:
    return _CALL_COUNT


def fetch_price_flaky(sku: str, *, fail_times: int = 2) -> str:
    """假装调外网查价：前 fail_times 次失败，之后返回成功。"""
    global _CALL_COUNT
    _CALL_COUNT += 1
    attempt = _CALL_COUNT
    if attempt <= fail_times:
        raise ConnectionError(f"模拟网络抖动：第 {attempt} 次调用失败 (sku={sku})")
    price = {"SKU-1": 128.0, "SKU-2": 56.0}.get(sku.upper(), 0.0)
    return f"{sku.upper()} 现价 {price} 元（实时）"
