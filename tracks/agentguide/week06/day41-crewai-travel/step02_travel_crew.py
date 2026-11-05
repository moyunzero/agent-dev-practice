"""Day41 Lesson 2 — 旅行规划师 / 向导 / 预订专员（sequential Crew）。

人话：规划师定骨架 → 向导补 2～3 个点 → 预订专员给建议订什么（假想，不真下单）。

承接 Day39–40 的双人流水线；名单与工单改成三人。

官方依据：
  https://docs.crewai.com/en/quickstart
  https://docs.crewai.com/en/learn/llm-connections

运行：
  uv run python step02_travel_crew.py
"""

from __future__ import annotations

import os

from crewai import Agent, Crew, LLM, Process, Task

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def main() -> None:
    llm = LLM(model=f"ollama/{MODEL}", base_url=BASE_URL)

    planner = Agent(
        role="旅行规划师",
        goal="根据短途需求写出极短的行程骨架",
        backstory="你只定天数、节奏、主题，不列店名、不下单。",
        llm=llm,
        verbose=True,
    )
    guide = Agent(
        role="本地向导",
        goal="按骨架补 2～3 个可走的点，短句即可",
        backstory="你熟悉本地街区与吃法，不推翻整份行程，不谈下单。",
        llm=llm,
        verbose=True,
    )
    booker = Agent(
        role="预订专员",
        goal="根据前两步给出建议预订的短清单",
        backstory="你只写假想的交通/住宿/门票建议，绝不声称已经订好。",
        llm=llm,
        verbose=True,
    )

    plan_task = Task(
        description=(
            "需求：杭州两天一夜，预算不高，偏轻松。"
            "写出行程骨架：天数、每天节奏、主题。中文短条。不要店名长清单。"
        ),
        expected_output="一份极短的中文行程骨架",
        agent=planner,
    )
    guide_task = Task(
        description=(
            "根据规划师的骨架，列出 2～3 个杭州可走的点（景点或街区或吃法）。"
            "每点一句中文。不要推翻骨架。"
        ),
        expected_output="2～3 条中文短推荐",
        agent=guide,
        context=[plan_task],
    )
    book_task = Task(
        description=(
            "根据规划师骨架和向导推荐，给出 3 条以内「建议预订」清单"
            "（例如交通/住宿/门票的假想项）。必须写明这是建议，不是已完成订单。"
        ),
        expected_output="不超过 3 条中文建议预订",
        agent=booker,
        context=[plan_task, guide_task],
    )

    crew = Crew(
        agents=[planner, guide, booker],
        tasks=[plan_task, guide_task, book_task],
        process=Process.sequential,
        verbose=True,
    )

    print("=== 旅行小队 kickoff（planner → guide → booker）===\n")
    result = crew.kickoff()
    print("\n=== 最终结果 ===")
    print(result)


if __name__ == "__main__":
    main()
