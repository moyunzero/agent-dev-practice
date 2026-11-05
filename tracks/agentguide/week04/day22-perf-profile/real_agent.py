"""现有 Agent 系统（与 Week3 Day15 同构）：create_agent + 工具 + Ollama。

Day22 回炉用：对「真 Agent 调用」做 cProfile / py-spy，而不是假 sleep 流水线。
"""

from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def build_agent():
    return create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[get_word_length, add],
        system_prompt=(
            "你是严谨的助手。需要长度或加法时必须调用工具，禁止心算。"
            "先 get_word_length，再用返回的整数调用 add。"
        ),
    )


def run_agent(question: str) -> str:
    """跑一轮 Agent，返回最终 Answer 文本。"""
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return "(no final answer)"
