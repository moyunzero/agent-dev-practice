"""第 1 课：没有对话记忆时，第二轮常「忘了」你是谁。"""

from __future__ import annotations

import os

from langchain.agents import create_agent

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def last_text(result: dict) -> str:
    msg = result["messages"][-1]
    content = getattr(msg, "content", "") or ""
    return content if isinstance(content, str) else str(content)


def main() -> None:
    # 故意：不传 checkpointer → 每次 invoke 互不记得
    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[],
        system_prompt="你是简洁助手。用一两句话回答。",
    )

    print("=== 无 Memory / 无 checkpointer：两轮各自独立 ===\n")

    r1 = agent.invoke({"messages": [{"role": "user", "content": "你好，我叫墨云。请记住我的名字。"}]})
    print("轮1 Q: 你好，我叫墨云。请记住我的名字。")
    print("轮1 A:", last_text(r1))
    print()

    r2 = agent.invoke({"messages": [{"role": "user", "content": "我叫什么名字？"}]})
    print("轮2 Q: 我叫什么名字？")
    print("轮2 A:", last_text(r2))
    print()
    print("观察：第二轮请求里只有「我叫什么名字？」，没有带上轮1的历史。")
    print("所以上游要 ConversationBufferMemory：把历史消息缓冲进后续请求。")


if __name__ == "__main__":
    main()
