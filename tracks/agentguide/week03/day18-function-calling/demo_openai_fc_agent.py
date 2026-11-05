"""第 2 课：OpenAI SDK Function Calling 最小 Agent 循环。

默认：Ollama OpenAI 兼容接口（与 Day1/2 相同）。
真 OpenAI：OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.openai.com/v1 OPENAI_MODEL=gpt-4o-mini
"""

from __future__ import annotations

import json
import os
import sys

from openai import OpenAI

# --- 假订单库：函数「真实执行」的数据源 ---
ORDERS = {
    "ORD-1001": {"status": "运输中", "city": "杭州", "eta": "2026-09-02"},
    "ORD-1002": {"status": "待支付", "city": "上海", "eta": None},
    "ORD-1003": {"status": "运输中", "city": "北京", "eta": "2026-08-20"},
}


def get_order_status(order_id: str) -> dict:
    """本地真函数：查订单。模型不会自动跑到这里，要靠我们根据 tool_calls 调用。"""
    key = order_id.strip().upper()
    info = ORDERS.get(key)
    if not info:
        return {"order_id": key, "error": "订单不存在"}
    return {"order_id": key, **info}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "根据订单号查询物流状态、收件城市与预计到达日。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 ORD-1001",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]

DISPATCH = {
    "get_order_status": get_order_status,
}


def make_client() -> tuple[OpenAI, str]:
    base_url = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")
    api_key = os.getenv("OPENAI_API_KEY", "ollama")
    model = os.getenv("OPENAI_MODEL", os.getenv("OLLAMA_MODEL", "qwen2:7b"))
    return OpenAI(base_url=base_url, api_key=api_key), model


def run_agent(question: str) -> None:
    client, model = make_client()
    messages: list[dict] = [
        {
            "role": "system",
            "content": "你是客服助手。查订单状态时必须调用 get_order_status，禁止编造。",
        },
        {"role": "user", "content": question},
    ]

    print(f"model={model}")
    print(f"Q: {question}\n")
    print("--- 第 1 轮：带 tools 请求模型 ---")

    resp1 = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    msg1 = resp1.choices[0].message
    print(f"finish_reason≈ {resp1.choices[0].finish_reason}")
    print(f"content: {msg1.content!r}")

    if not msg1.tool_calls:
        print("未收到 tool_calls。可换支持 tools 的模型，或设 OPENAI_API_KEY 用真 OpenAI。")
        if msg1.content:
            print("Answer:", msg1.content)
        return

    # 把 assistant 消息（含 tool_calls）追加进历史
    messages.append(msg1.model_dump(exclude_none=True))

    print("\n--- 执行本地函数（模型点的菜单）---")
    for call in msg1.tool_calls:
        name = call.function.name
        args = json.loads(call.function.arguments or "{}")
        print(f"tool_call id={call.id}")
        print(f"  name={name} args={args}")
        fn = DISPATCH.get(name)
        if fn is None:
            result = {"error": f"未知函数 {name}"}
        else:
            result = fn(**args)
        print(f"  函数返回: {result}")
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    print("\n--- 第 2 轮：把函数结果交回模型，生成最终答案 ---")
    resp2 = client.chat.completions.create(
        model=model,
        messages=messages,
    )
    final = resp2.choices[0].message.content
    print("Answer:", final)


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "帮我查一下订单 ORD-1001 现在什么状态？"
    run_agent(question)


if __name__ == "__main__":
    main()
