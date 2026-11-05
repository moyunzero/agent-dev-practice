"""Day36–37 Lesson 2 — 现役 AgentChat：单 AssistantAgent（对齐官方 Quickstart 风格）。

官方依据：
  - https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/quickstart.html
  - Ollama 客户端：autogen_ext.models.ollama.OllamaChatCompletionClient

前置：ollama serve；已 pull 模型（默认 llama3.1:8b，可用环境变量 OLLAMA_MODEL 覆盖）

运行：
  uv sync
  uv run python step02_assistant_hello.py
"""

from __future__ import annotations

import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.ollama import OllamaChatCompletionClient

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


async def main() -> None:
    # 1) 接通本机 Ollama（「脑子」的接线员）
    model_client = OllamaChatCompletionClient(model=MODEL)

    # 2) 雇一个只会聊天的助手；system_message = 给它的工作规矩
    agent = AssistantAgent(
        "assistant",
        model_client=model_client,
        system_message="你是简洁助手。回答尽量短。",
    )

    # 3) 把任务交给助手，等待它问完模型、拿到回答
    result = await agent.run(task="用一句话介绍你自己。只输出一句中文。")

    # 4) 打印结果：整盒对话 + 最后一句（助手的回答）
    print("--- TaskResult（整段对话记录）---")
    print(result)
    print("--- 助手最后一句 ---")
    if result.messages:
        last = result.messages[-1]
        print(getattr(last, "content", last))

    # 5) 用完关掉连接
    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
