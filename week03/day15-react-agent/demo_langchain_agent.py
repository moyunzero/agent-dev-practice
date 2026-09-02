"""第 1 课（下）：LangChain 官方风格 Agent — create_agent + @tool + Ollama。"""

from __future__ import annotations

import os
import sys

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, ToolMessage

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _text(content) -> str:
    return content if isinstance(content, str) else str(content)


def print_react_trace(messages: list) -> None:
    """把 LangGraph 消息流映射回 Thought / Action / Observation。

    Answer 只取最后一条无 tool_calls 的 AIMessage，避免中间推理被误标。
    """
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
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "单词 agent 有几个字母？把结果加10"
    )

    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[get_word_length, add],
        system_prompt=(
            "你是严谨的助手。需要长度或加法时必须调用工具，禁止心算。"
            "先 get_word_length，再用返回的整数调用 add。"
        ),
    )

    print(f"Q: {question}\n")
    print("--- ReAct 轨迹 ---")

    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    print_react_trace(result["messages"])


if __name__ == "__main__":
    main()
