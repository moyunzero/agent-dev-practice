"""第 2 课：把查天气工具挂进 create_agent（需 Ollama）。"""

from __future__ import annotations

import os
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from step01_weather_tool import get_weather

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def _text(content) -> str:
    return content if isinstance(content, str) else str(content)


def print_react_trace(messages: list) -> None:
    step = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                for call in msg.tool_calls:
                    step += 1
                    print(f"Thought {step}: 模型决定调用 {call['name']}")
                    print(f"Action {step}: {call['name']}({call['args']})")
                text = _text(msg.content).strip() if msg.content else ""
                if text:
                    print(f"(中间文本) {text}")
        elif isinstance(msg, ToolMessage):
            print(f"Observation: {msg.content}")

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            text = _text(msg.content).strip() if msg.content else ""
            if text:
                print(f"Answer: {text}")
            break


def main() -> None:
    question = sys.argv[1] if len(sys.argv) > 1 else "北京今天天气怎么样？"

    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[get_weather],
        system_prompt=(
            "你是天气助手。用户问天气时必须调用 get_weather 工具，禁止编造气温。"
            "城市名用中文，例如北京、上海、深圳。"
        ),
    )

    print(f"Q: {question}\n")
    print("--- ReAct 轨迹 ---")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    print_react_trace(result["messages"])


if __name__ == "__main__":
    main()
