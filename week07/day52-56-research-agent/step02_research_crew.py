"""Day52–56 Lesson 4 — 三人 sequential Crew + 中间产出落盘。

人话：搜集 → 分析 → 撰写；每步结果写入 intermediate/，最后一份再调写文件工具。

承接：Day41 旅行小队同形；工具来自 research_tools.py。

运行（需本机 Ollama）：
  uv run python step02_research_crew.py
"""

from __future__ import annotations

import os
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task

from research_tools import (
    company_overview,
    parse_filing_metrics,
    sec_filings_search,
    web_search,
    write_report_file,
)

ROOT = Path(__file__).resolve().parent
INTERMEDIATE = ROOT / "intermediate"
COMPANY = os.getenv("RESEARCH_COMPANY", "Acme Corp")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def _save_step(name: str, text: str) -> Path:
    INTERMEDIATE.mkdir(parents=True, exist_ok=True)
    path = INTERMEDIATE / name
    path.write_text(str(text), encoding="utf-8")
    print(f"[中间产出] {path}")
    return path


def main() -> None:
    llm = LLM(model=f"ollama/{MODEL}", base_url=BASE_URL)

    researcher = Agent(
        role="信息搜集 Agent",
        goal="搜集目标公司的公开信息与基本面摘要，写成短笔记",
        backstory="你只汇总公开信息与链接，不算财报指标，不荐股。",
        llm=llm,
        tools=[web_search, company_overview],
        verbose=True,
    )
    analyst = Agent(
        role="财报分析 Agent",
        goal="查申报条目并抽取可复算关键指标，写成指标/要点稿",
        backstory="你只做财报条目与指标，不写长报告，不荐股。",
        llm=llm,
        tools=[sec_filings_search, parse_filing_metrics],
        verbose=True,
    )
    writer = Agent(
        role="报告撰写 Agent",
        goal="综合搜集笔记与指标稿，写成结构化中文报告并落盘",
        backstory="你只根据前两步产出写报告，不编造数字，不给出买入/卖出建议。",
        llm=llm,
        tools=[write_report_file],
        verbose=True,
    )

    research_task = Task(
        description=(
            f"公司：{COMPANY}。"
            "用工具搜集公开信息与公司简介，输出中文短笔记（含要点与来源链接）。"
            "不要计算财报指标，不要荐股。"
        ),
        expected_output="一份中文搜集笔记（摘要+链接）",
        agent=researcher,
    )
    analysis_task = Task(
        description=(
            f"公司：{COMPANY}。"
            "根据搜集笔记，用工具查 SEC/财报条目并抽取关键指标，"
            "输出可对账的指标/要点稿。不要写长报告，不要荐股。"
        ),
        expected_output="一份中文指标/要点稿（含营收等关键数字）",
        agent=analyst,
        context=[research_task],
    )
    write_task = Task(
        description=(
            f"公司：{COMPANY}。"
            "综合搜集笔记与指标稿，写一份短中文结构化报告（背景/要点/指标/风险提示）。"
            "禁止买入/卖出建议。写完后必须调用 write_report_file 把全文写入文件。"
        ),
        expected_output="报告正文摘要 + 已写入的文件路径",
        agent=writer,
        context=[research_task, analysis_task],
    )

    crew = Crew(
        agents=[researcher, analyst, writer],
        tasks=[research_task, analysis_task, write_task],
        process=Process.sequential,
        verbose=True,
    )

    print(f"=== 投研小队 kickoff（{COMPANY}）===\n")
    result = crew.kickoff()

    # 中间产出：按 Task 顺序落盘，便于审计「每步做没做」
    _save_step("01_research.md", research_task.output)
    _save_step("02_analysis.md", analysis_task.output)
    _save_step("03_writer.md", write_task.output)

    print("\n=== 最终结果 ===")
    print(result)


if __name__ == "__main__":
    main()
