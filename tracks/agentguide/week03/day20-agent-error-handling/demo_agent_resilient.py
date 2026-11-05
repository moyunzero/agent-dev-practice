"""第 3 课：把韧性查价挂进 create_agent。"""

from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from flaky_price import CACHE_PRICE, fetch_price_flaky, reset_counter

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.1),
    reraise=True,
)
def _fetch_live(sku: str) -> str:
    return fetch_price_flaky(sku, fail_times=2)


@tool
def lookup_price(sku: str) -> str:
    """查询商品现价。参数 sku 例如 SKU-1 或 SKU-2。失败时会重试，仍失败则返回缓存价。"""
    try:
        return _fetch_live(sku)
    except ConnectionError as e:
        cached = CACHE_PRICE.get(sku.upper())
        if cached is not None:
            return f"{sku.upper()} 实时失败，降级缓存价 {cached} 元。（{e}）"
        return f"查询失败：{e}"


def main() -> None:
    reset_counter()
    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[lookup_price],
        system_prompt="你是导购。问价格必须调用 lookup_price，禁止编造数字。用一句话回答。",
    )
    q = "SKU-1 现在多少钱？"
    print(f"Q: {q}\n")
    result = agent.invoke({"messages": [{"role": "user", "content": q}]})
    for msg in result["messages"]:
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            print("Answer:", msg.content)
            break


if __name__ == "__main__":
    main()
