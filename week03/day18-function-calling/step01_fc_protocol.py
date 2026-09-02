"""第 1 课：Function Calling 协议长什么样（不调模型）。"""

from __future__ import annotations

import json

# 发给 API 的 tools：告诉模型「你可以请求调用这些函数」
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "根据订单号查询物流状态与收件城市。",
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

# 模型若决定调用，响应里会出现类似结构（示意）
FAKE_ASSISTANT_TOOL_CALL = {
    "role": "assistant",
    "content": None,
    "tool_calls": [
        {
            "id": "call_demo_1",
            "type": "function",
            "function": {
                "name": "get_order_status",
                "arguments": '{"order_id": "ORD-1001"}',
            },
        }
    ],
}


def main() -> None:
    print("=== Day15–17：LangChain @tool + create_agent（框架帮你填协议）===")
    print("=== Day18：直接看 OpenAI Chat Completions 的 tools / tool_calls ===\n")

    print("--- 1) 你发给 API 的 tools（函数说明书 / JSON Schema）---")
    print(json.dumps(TOOLS, ensure_ascii=False, indent=2))

    print("\n--- 2) 模型可能返回的 tool_calls（「请你去调这个函数」）---")
    print(json.dumps(FAKE_ASSISTANT_TOOL_CALL, ensure_ascii=False, indent=2))

    print("\n--- 3) 分工 ---")
    print("  模型：只决定「调谁、参数是什么」，不执行你的 Python")
    print("  你的程序：解析 tool_calls → 调用真函数 → 把结果再塞回对话")
    print("  模型（第二轮）：读到函数结果后，写给人看的答案")
    print("\n要点：Function Calling ≠ 模型能跑代码；是约定好的「点菜单」协议。")


if __name__ == "__main__":
    main()
