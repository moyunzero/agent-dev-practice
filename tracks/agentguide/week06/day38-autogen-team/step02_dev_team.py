"""Day38 Lesson 2 — 研究员 / 程序员 / 测试员 三人轮转（RoundRobinGroupChat）。

人话：研究员拆需求 → 程序员写短实现 → 测试员列用例或 APPROVE → 轮流直到同意或条数上限。

承接 Day36–37 的双人会议室；名单改成三人。

官方依据：
  https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html
  https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html

运行：
  uv run python step02_dev_team.py
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

    # 2) 雇三个助手（不同工牌、不同规矩）
    researcher = AssistantAgent(
        name="researcher",
        model_client=model_client,
        system_message=(
            "你是研究员。把用户需求拆成极短的要点："
            "目标、输入、输出、约束。用中文条目列出，不要写代码。"
        ),
    )
    coder = AssistantAgent(
        name="coder",
        model_client=model_client,
        system_message=(
            "你是程序员。根据研究员的要点，用 Python 写一个很短的函数实现。"
            "只输出代码，不要长篇解释。"
        ),
    )
    tester = AssistantAgent(
        name="tester",
        model_client=model_client,
        system_message=(
            "你是测试员。根据程序员的代码，列出 2～3 条简短测试用例（中文）。"
            "若实现清楚且可测，只回复：APPROVE。"
            "否则只指出一个问题，不要重写全部代码。"
        ),
    )

    # 3) 散会：测试员 APPROVE，或消息太多（三人一轮就要更多条）
    termination = TextMentionTermination("APPROVE") | MaxMessageTermination(9)

    # 4) 会议室：按名单轮流 researcher → coder → tester → …
    team = RoundRobinGroupChat(
        [researcher, coder, tester],
        termination_condition=termination,
    )

    # 5) 丢进短任务，一条条打印
    print("=== 三人小队开始协作（看到 researcher / coder / tester 交替即可）===\n")
    await Console(
        team.run_stream(
            task=(
                "写一个 Python 函数 celsius_to_fahrenheit(c: float) -> float，"
                "把摄氏度转成华氏度。要求：短小、可测。"
            )
        )
    )

    # 6) 关掉接线员
    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
