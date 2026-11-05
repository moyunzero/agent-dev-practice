"""Day52–56 Lesson 3 — 投研工具集（≥5）。

人话：五只「手」——搜网、公司简介、查申报、算指标、写报告文件。
默认读 fixtures/（无 Key / 离线也能跑）；签名固定，换实现不换挂载方式。

官方：https://docs.crewai.com/en/concepts/tools
"""

from __future__ import annotations

import json
from pathlib import Path

from crewai.tools import tool

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
OUTPUT = ROOT / "output"


def _load_json(name: str) -> dict:
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(company: str) -> str:
    return company.strip().lower().replace(" ", "_")


@tool("Web Search")
def web_search(query: str) -> str:
    """搜索公开网页，返回简短摘要与链接。问新闻、公开资料时用。"""
    # 本课：fixture 等价 Google Search；有网络时可换成 DDGS
    return (
        f"[fixture web_search] query={query!r}\n"
        "1. Acme 工业传感器扩产 — 来源: https://example.com/acme-expand\n"
        "2. Acme FY2024 营收摘要 — 来源: https://example.com/acme-fy2024"
    )


@tool("Company Overview")
def company_overview(company: str) -> str:
    """按公司名返回简介、行业、交易所等基本面摘要。"""
    data = _load_json("acme_overview.json")
    if "acme" not in company.lower():
        return f"[fixture] 暂无 {company!r} 的 overview；演示请用 Acme Corp。"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool("SEC Filings Search")
def sec_filings_search(company: str) -> str:
    """查询公司近期 SEC 申报/财报条目（表单类型、日期、链接）。"""
    data = _load_json("acme_filings.json")
    if "acme" not in company.lower():
        return f"[fixture] 暂无 {company!r} 的 filings；演示请用 Acme Corp。"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool("Parse Filing Metrics")
def parse_filing_metrics(company: str) -> str:
    """从财报文本/fixture 抽取可复算关键指标（营收、净利、毛利率等）。"""
    data = _load_json("acme_metrics.json")
    if "acme" not in company.lower():
        return f"[fixture] 暂无 {company!r} 的指标；演示请用 Acme Corp。"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool("Write Report File")
def write_report_file(company: str, content: str) -> str:
    """把报告正文写入 output/<公司>_report.md，返回文件路径。"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"{_slug(company)}_report.md"
    path.write_text(content, encoding="utf-8")
    return f"已写入: {path}"
