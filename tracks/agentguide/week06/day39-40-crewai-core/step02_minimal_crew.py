"""Day39–40 Lesson 2 — 最小 sequential Crew（Agent + Task + Crew + Process）。

人话：研究员先列 3 条要点 → 写手根据要点写一句中文口号 → kickoff 开机。

官方依据：
  https://docs.crewai.com/en/quickstart
  https://docs.crewai.com/en/learn/llm-connections  （Ollama: LLM(model=\"ollama/...\", base_url=...)）

运行：
  uv run python step02_minimal_crew.py
"""

from __future__ import annotations

import os

from crewai import Agent, Crew, LLM, Process, Task

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def main() -> None:
    # 1) 接线员：官方 LLM 类 + ollama/ 前缀（走 LiteLLM）
    llm = LLM(model=f"ollama/{MODEL}", base_url=BASE_URL)

    # 2) 两个 Agent（role / goal / backstory）
    researcher = Agent(
        role="产品研究员",
        goal="把产品需求拆成极短、可执行的要点",
        backstory="你擅长把模糊需求写成三条以内的清晰条目，从不写长文。",
        llm=llm,
        verbose=True,
    )
    writer = Agent(
        role="文案写手",
        goal="根据要点写出一句短、好记的中文口号",
        backstory="你只输出一句口号，不解释、不加前后缀。",
        llm=llm,
        verbose=True,
    )

    # 3) 两个 Task（后一个用 context 接上一个的结果）
    research_task = Task(
        description=(
            "为「本地笔记 App」列出恰好 3 条产品卖点要点（中文短句）。"
            "不要写口号，不要编号以外的废话。"
        ),
        expected_output="恰好 3 条中文短要点",
        agent=researcher,
    )
    write_task = Task(
        description=(
            "根据研究员给出的 3 条要点，写一句中文产品口号。"
            "只要一句，要短、好记。"
        ),
        expected_output="一句中文口号",
        agent=writer,
        context=[research_task],
    )

    # 4) Crew + Process.sequential → kickoff
    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential,
        verbose=True,
    )

    print("=== Crew kickoff（sequential：先研究后写）===\n")
    result = crew.kickoff()
    print("\n=== 最终结果 ===")
    print(result)


if __name__ == "__main__":
    main()
