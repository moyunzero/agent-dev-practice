"""Day36–37 Lesson 3 — 两个助手轮流说话（RoundRobinGroupChat）。

人话：写手写一句口号 → 评审说 APPROVE 或给建议 → 轮流直到同意或达到条数上限。

官方依据：
  https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html
  （RoundRobinGroupChat + TextMentionTermination 示例）

运行：
  uv run python step03_roundrobin_two_agents.py
"""

from __future__ import annotations

import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.ollama import OllamaChatCompletionClient

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


async def main() -> None:
    # 1) 同一个接线员，接本机 Ollama
    model_client = OllamaChatCompletionClient(model=MODEL)

    # 2) 雇两个助手（不同工牌、不同规矩）
    writer = AssistantAgent(
        name="writer",
        model_client=model_client,
        system_message=(
            "你是写手。根据任务写一句很短的中文产品口号。"
            "每次只输出一句口号，不要解释。"
        ),
    )
    critic = AssistantAgent(
        name="critic",
        model_client=model_client,
        system_message=(
            "你是评审。若口号清楚好记，只回复：APPROVE。"
            "否则只回复一句简短修改建议（中文）。不要长篇大论。"
        ),
    )

    # 3) 什么时候散会：有人说 APPROVE，或消息太多（防止一直聊）
    termination = TextMentionTermination("APPROVE") | MaxMessageTermination(6)

    # 4) 会议室：按名单轮流（写手 → 评审 → 写手 → …）
    team = RoundRobinGroupChat(
        [writer, critic],
        termination_condition=termination,
    )

    # 5) 丢进任务，一条条打印到终端
    print("=== 两个助手开始轮流说话（看到 writer / critic 交替即可）===\n")
    await Console(
        team.run_stream(
            task="为「本地笔记 App」写一句中文口号。要短、好记。"
        )
    )

    # 6) 关掉接线员
    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
