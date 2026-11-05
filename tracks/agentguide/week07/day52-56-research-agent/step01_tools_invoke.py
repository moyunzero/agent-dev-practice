"""Day52–56 Lesson 3 — 不经过 Agent，直接 invoke 五个工具。

人话：先确认「手」本身能干活，再挂到三人身上（下一课 Crew）。

运行：
  uv run python step01_tools_invoke.py
"""

from __future__ import annotations

from research_tools import (
    company_overview,
    parse_filing_metrics,
    sec_filings_search,
    web_search,
    write_report_file,
)

COMPANY = "Acme Corp"


def main() -> None:
    print("=== 1 web_search ===")
    print(web_search.run(query=f"{COMPANY} news"))

    print("\n=== 2 company_overview ===")
    print(company_overview.run(company=COMPANY))

    print("\n=== 3 sec_filings_search ===")
    print(sec_filings_search.run(company=COMPANY))

    print("\n=== 4 parse_filing_metrics ===")
    print(parse_filing_metrics.run(company=COMPANY))

    print("\n=== 5 write_report_file ===")
    draft = f"# {COMPANY} 演示报告\n\n（本步只测写文件工具）\n"
    print(write_report_file.run(company=COMPANY, content=draft))


if __name__ == "__main__":
    main()
