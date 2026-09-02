"""第 2 课：InMemorySaver + thread_id ≈ ConversationBufferMemory 效果。"""

from __future__ import annotations

import os

from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def last_text(result: dict) -> str:
    msg = result["messages"][-1]
    content = getattr(msg, "content", "") or ""
    return content if isinstance(content, str) else str(content)


def main() -> None:
    # checkpointer：会话状态存哪里；InMemory = 进程内缓冲（类似 BufferMemory）
    memory = InMemorySaver()
    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[],
        checkpointer=memory,
        system_prompt="你是简洁助手。记住用户说过的个人信息，用一两句话回答。",
    )

    same_thread = {"configurable": {"thread_id": "chat-墨墨"}}
    other_thread = {"configurable": {"thread_id": "chat-路人"}}

    print("=== 同一 thread_id：应记住名字（缓冲历史）===\n")
    r1 = agent.invoke(
        {"messages": [{"role": "user", "content": "你好，我叫墨墨。请记住我的名字。"}]},
        config=same_thread,
    )
    print("轮1 Q: 你好，我叫墨墨。请记住我的名字。")
    print("轮1 A:", last_text(r1))
    print()

    r2 = agent.invoke(
        {"messages": [{"role": "user", "content": "我叫什么名字？"}]},
        config=same_thread,
    )
    print("轮2 Q: 我叫什么名字？  (thread=chat-墨云)")
    print("轮2 A:", last_text(r2))
    print()

    print("=== 换一个 thread_id：新会话，不应依赖墨云的历史 ===\n")
    r3 = agent.invoke(
        {"messages": [{"role": "user", "content": "我叫什么名字？"}]},
        config=other_thread,
    )
    print("轮3 Q: 我叫什么名字？  (thread=chat-路人)")
    print("轮3 A:", last_text(r3))
    print()
    print("对照上游：ConversationBufferMemory = 缓冲对话消息；")
    print("现版落地：checkpointer + 同一 thread_id 自动带上历史 messages。")


if __name__ == "__main__":
    main()
