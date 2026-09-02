"""第 2 课：研究助手 Agent — RAG + Web 双工具。"""

from __future__ import annotations

import os
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from rag_store import get_vectorstore
from research_tools import search_knowledge_base, web_search

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def _text(content) -> str:
    return content if isinstance(content, str) else str(content)


def print_trace(messages: list) -> None:
    step = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                step += 1
                print(f"Thought {step}: 调用 {call['name']}")
                print(f"Action {step}: {call['name']}({call['args']})")
        elif isinstance(msg, ToolMessage):
            preview = _text(msg.content)
            if len(preview) > 240:
                preview = preview[:240] + "…"
            print(f"Observation: {preview}")

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            text = _text(msg.content).strip() if msg.content else ""
            if text:
                print(f"Answer: {text}")
            break


def main() -> None:
    get_vectorstore()  # 确保索引存在；已有则直接加载
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Nebula Router 的内部协议版本和桶数分别是什么？请依据知识库回答。"
    )

    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[search_knowledge_base, web_search],
        system_prompt=(
            "你是研究助手。内部/私有项目细节必须调用 search_knowledge_base；"
            "公开新闻与通用概念调用 web_search。"
            "禁止编造 N7 / Nebula 细节。根据工具结果用中文简洁回答。"
        ),
    )

    print(f"Q: {question}\n")
    print("--- 轨迹 ---")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    print_trace(result["messages"])


if __name__ == "__main__":
    main()
