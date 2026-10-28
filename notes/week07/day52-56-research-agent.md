# 用 CrewAI 搭自动化投研流水线：搜集 → 财报分析 → 撰写

分析师丢进一个**公司名**，希望系统自动：搜公开信息、抽可复算指标、写成报告——中间每一步还能对账。  
本文用 CrewAI 三人顺序小队 + 至少五个工具 + 中间产出落盘 + 工具重试/降级，从空目录跑通这条流水线。付费搜索/SEC Key 可用 fixture 等价替代，工具种类不缩水。

## 你将会得到什么

1. 钉死需求边界：输入公司名；三步产出；**不荐股**  
2. 三人 Agent 分工与 `context` 交接  
3. ≥5 个工具（搜索、基本面、SEC 条目、指标、写文件）并可单独 invoke  
4. `Process.sequential` + 每步写入 `intermediate/`  
5. 用 tenacity 演示重试与降级，理解「成功率 >95%」在本课的口径  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### Multi-Agent（多智能体）与三人分工

| 层 | 说明 |
|----|------|
| **是什么** | 多个带角色的 Agent 协作，而不是一个模型包办全部 |
| **在本文干什么** | 信息搜集 / 财报分析 / 报告撰写各管一段 |
| **怎么区分** | 单 Agent 也能调工具，但难审计「分析步有没有独立产出」；三人 + 中间稿才能对账 |

### CrewAI：Agent / Task / Crew / Process.sequential

| 层 | 说明 |
|----|------|
| **是什么** | Agent=角色；Task=工单；Crew=小队；`sequential`=按任务列表顺序执行 |
| **在本文干什么** | 搜集 Task → 分析 Task → 撰写 Task，一次 `kickoff()` |
| **怎么区分** | sequential 只保证**谁先跑**；下一任能否读到上一任文字，靠 Task 的 `context=[...]` |

### context 接力

| 层 | 说明 |
|----|------|
| **是什么** | 后一张 Task 声明依赖的前序 Task，运行时把前序产出塞进提示 |
| **在本文干什么** | 分析读搜集笔记；撰写读搜集+指标稿 |
| **怎么区分** | 没有 `context` 时，后面的人往往只看见自己 description 里的公司名，交接物断掉 |

### 工具（Tool）

| 层 | 说明 |
|----|------|
| **是什么** | Agent 可调用的函数（查网、读 JSON、写文件） |
| **在本文干什么** | 五只手按职责挂给对应 Agent；先不经 Agent 用 `.run()` 测通 |
| **怎么区分** | Agent 决定「要想什么」；工具负责「真去查/写」。没工具时模型容易瞎编数字 |

### fixture（教学替身）

| 层 | 说明 |
|----|------|
| **是什么** | 预先写好的本地样例数据，形状对齐真实 API 返回 |
| **在本文干什么** | `fixtures/acme_*.json` 顶替 Google Search / SEC，无 Key 也能跑通种类与挂载 |
| **怎么区分** | fixture ≠ 实时行情；报告与笔记应标明数据来源，不能假装刚爬到的 SEC |

### 重试（retry）与降级（fallback）

| 层 | 说明 |
|----|------|
| **是什么** | 重试=偶发失败再试；降级=试尽了仍返回可读文本（fixture/缓存） |
| **在本文干什么** | `tenacity` 包一层抖动搜索；耗尽则 `[fixture 降级]` |
| **怎么区分** | 只重试不降级 → 服务一直挂时整条流水线硬断；降级不假装「实时搜到」 |

### 成功率 >95%（本课口径）

| 层 | 说明 |
|----|------|
| **是什么** | 上游对稳定性的量化说法 |
| **在本文干什么** | 理解为：可控抖动下，工具**多数时候仍交出可用文本**（重试成功或降级兜底） |
| **怎么区分** | 不是「模型永不胡说」，也不是「永远命中真网」 |

```text
公司名
  → 搜集 Agent（web_search + company_overview）→ intermediate/01_*.md
  → 分析 Agent（sec_filings_search + parse_filing_metrics）→ 02_*.md
  → 撰写 Agent（write_report_file）→ 03_*.md + output/*_report.md
```

---

## 环境准备

- Python ≥3.10（建议 3.12）+ [uv](https://github.com/astral-sh/uv)  
- 本机 [Ollama](https://ollama.com/) 已启动，并已拉取模型（示例：`llama3.1:8b`）  
- 验证 Ollama：`curl -s http://127.0.0.1:11434/api/tags` 应返回 JSON  

可选环境变量：

| 变量 | 默认 | 含义 |
|------|------|------|
| `OLLAMA_MODEL` | `llama3.1:8b` | 模型名 |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama 地址 |
| `RESEARCH_COMPANY` | `Acme Corp` | 演示公司名 |
| `RETRY_ATTEMPTS` | `3` | 重试演示最多尝试次数 |

---

## 动手：空目录骨架

```bash
mkdir -p research-agent/{fixtures,output,intermediate}
cd research-agent
```

`pyproject.toml`：

```toml
[project]
name = "research-agent-demo"
version = "0.1.0"
requires-python = ">=3.10,<3.14"
dependencies = [
  "crewai[litellm]==1.15.20",
  "tenacity>=8.0.0",
]
```

然后：

```bash
uv sync
```

### fixtures（演示公司 Acme Corp）

`fixtures/acme_overview.json`：

```json
{
  "company": "Acme Corp",
  "ticker": "ACME",
  "exchange": "NASDAQ",
  "industry": "工业自动化",
  "summary": "Acme 生产工业传感器与边缘网关，主要客户为制造业 OEM。"
}
```

`fixtures/acme_filings.json`：

```json
{
  "company": "Acme Corp",
  "filings": [
    {
      "form": "10-K",
      "filed": "2025-03-01",
      "period": "FY2024",
      "url": "fixture://acme/10-K-2024"
    },
    {
      "form": "10-Q",
      "filed": "2025-08-15",
      "period": "Q2-2025",
      "url": "fixture://acme/10-Q-2025Q2"
    }
  ]
}
```

`fixtures/acme_metrics.json`：

```json
{
  "company": "Acme Corp",
  "period": "FY2024",
  "revenue_usd_m": 420.5,
  "net_income_usd_m": 38.2,
  "gross_margin_pct": 42.5,
  "notes": "数字来自 fixtures，非实时 SEC；仅供流水线演示与对账。"
}
```

---

## 五个工具

`research_tools.py`（核心：`@tool` + 读 fixture / 写文件）：

```python
from __future__ import annotations

import json
from pathlib import Path

from crewai.tools import tool

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "fixtures"
OUTPUT = ROOT / "output"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _slug(company: str) -> str:
    return company.strip().lower().replace(" ", "_")


@tool("Web Search")
def web_search(query: str) -> str:
    """搜索公开网页，返回简短摘要与链接。"""
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
    """查询公司近期 SEC 申报/财报条目。"""
    data = _load_json("acme_filings.json")
    if "acme" not in company.lower():
        return f"[fixture] 暂无 {company!r} 的 filings；演示请用 Acme Corp。"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool("Parse Filing Metrics")
def parse_filing_metrics(company: str) -> str:
    """从财报/fixture 抽取可复算关键指标。"""
    data = _load_json("acme_metrics.json")
    if "acme" not in company.lower():
        return f"[fixture] 暂无 {company!r} 的指标；演示请用 Acme Corp。"
    return json.dumps(data, ensure_ascii=False, indent=2)


@tool("Write Report File")
def write_report_file(company: str, content: str) -> str:
    """把报告正文写入 output/<公司>_report.md。"""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    path = OUTPUT / f"{_slug(company)}_report.md"
    path.write_text(content, encoding="utf-8")
    return f"已写入: {path}"
```

先不经 Agent 测手：

```python
# step01_tools_invoke.py
from research_tools import (
    company_overview,
    parse_filing_metrics,
    sec_filings_search,
    web_search,
    write_report_file,
)

COMPANY = "Acme Corp"

print(web_search.run(query=f"{COMPANY} news"))
print(company_overview.run(company=COMPANY))
print(sec_filings_search.run(company=COMPANY))
print(parse_filing_metrics.run(company=COMPANY))
print(write_report_file.run(company=COMPANY, content=f"# {COMPANY}\n"))
```

```bash
uv run python step01_tools_invoke.py
```

**期望**：五段都有输出；`output/acme_corp_report.md` 被创建。改 `fixtures/acme_metrics.json` 里某个数再跑，第 4 段应跟着变——说明工具读的是数据层，不是写死在函数里。

| 工具 | 挂给谁 | 等价上游 |
|------|--------|----------|
| `web_search` | 搜集 | Google Search |
| `company_overview` | 搜集 | 公司基本面 API |
| `sec_filings_search` | 财报分析 | SEC API |
| `parse_filing_metrics` | 财报分析 | 解析财报、算指标 |
| `write_report_file` | 撰写 | 文件读写 |

---

## 三人 sequential Crew + 中间产出

```python
# step02_research_crew.py（结构摘要）
from crewai import Agent, Crew, LLM, Process, Task
from research_tools import (
    company_overview,
    parse_filing_metrics,
    sec_filings_search,
    web_search,
    write_report_file,
)

llm = LLM(model="ollama/llama3.1:8b", base_url="http://127.0.0.1:11434")

researcher = Agent(
    role="信息搜集 Agent",
    goal="搜集公开信息与基本面摘要",
    backstory="不算指标，不荐股。",
    llm=llm,
    tools=[web_search, company_overview],
    verbose=True,
)
analyst = Agent(
    role="财报分析 Agent",
    goal="查申报并抽取可复算指标",
    backstory="不写长报告，不荐股。",
    llm=llm,
    tools=[sec_filings_search, parse_filing_metrics],
    verbose=True,
)
writer = Agent(
    role="报告撰写 Agent",
    goal="综合前两步写成报告并落盘",
    backstory="不编造数字，不给出买入/卖出建议。",
    llm=llm,
    tools=[write_report_file],
    verbose=True,
)

research_task = Task(
    description="公司：Acme Corp。用工具写中文搜集笔记（摘要+链接）。不要算指标，不要荐股。",
    expected_output="中文搜集笔记",
    agent=researcher,
)
analysis_task = Task(
    description="根据搜集笔记，查 filings 并抽指标，输出要点稿。不要荐股。",
    expected_output="指标/要点稿",
    agent=analyst,
    context=[research_task],
)
write_task = Task(
    description="综合笔记与指标稿写短报告；禁止买卖建议；必须调用 write_report_file。",
    expected_output="报告摘要 + 文件路径",
    agent=writer,
    context=[research_task, analysis_task],
)

crew = Crew(
    agents=[researcher, analyst, writer],
    tasks=[research_task, analysis_task, write_task],
    process=Process.sequential,
    verbose=True,
)
result = crew.kickoff()

# 中间产出落盘（审计用）
Path("intermediate").mkdir(exist_ok=True)
Path("intermediate/01_research.md").write_text(str(research_task.output), encoding="utf-8")
Path("intermediate/02_analysis.md").write_text(str(analysis_task.output), encoding="utf-8")
Path("intermediate/03_writer.md").write_text(str(write_task.output), encoding="utf-8")
print(result)
```

```bash
uv run python step02_research_crew.py
```

**期望**：日志按搜集 → 分析 → 撰写推进；`intermediate/` 下有三份文件。  
若删掉 `context=[research_task]`，分析步往往吃不到搜集笔记——sequential 保顺序，context 保交接。

### 新手坑：撰写「演」了工具调用

| | |
|--|--|
| **现象** | 最终答案是一段 `{"name":"write_report_file",...}` 文本；`output/` 时间戳没更新 |
| **原因** | 小模型有时把工具调用写成字符串，而不是真正触发工具 |
| **处理** | 收紧 `expected_output`（要求返回工具给出的路径）；必要时加大模型或人工把正文写入 `output/`；中间三份文件仍可用于审计分析步 |

遥测警告 `telemetry.crewai.com` SSL 失败可忽略，或运行前：`export OTEL_SDK_DISABLED=true`。

---

## 重试与降级

```python
# step03_retry_fallback.py（核心）
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.1),
    reraise=True,
)
def search_with_retry(query: str) -> str:
    # 前两次 raise ConnectionError，第三次返回 live 文本（教学用）
    ...

def search_resilient(query: str) -> str:
    try:
        return search_with_retry(query)
    except ConnectionError:
        return f"[fixture 降级] query={query!r}\n..."
```

```bash
uv run python step03_retry_fallback.py
# 把尝试次数压到 2，应看到 A 段降级：
RETRY_ATTEMPTS=2 uv run python step03_retry_fallback.py
```

**期望**：默认 A 段最终 `[live]`；`RETRY_ATTEMPTS=2` 时 A 段变成 `[fixture 降级]`。

---

## 边界：做了什么 / 故意没做什么

| 做了 | 没做 |
|------|------|
| 公司名 → 三人顺序流 + ≥5 工具种类 | 真实荐股 / 买卖信号 |
| fixture 等价 Search / SEC | 强制付费 Google/SEC Key 才能开课 |
| 中间产出落盘可审计 | 保证小模型每次都正确触发写文件工具 |
| 重试 + 降级演示 | 生产级 SLA 监控与自动扩缩 |

---

## 小结

投研 Agent 的骨架不是「一个大 Prompt」，而是：**分工清晰的三人顺序流 + 按人挂工具 + context 交接 + 中间稿可对账 + 工具层扛抖动**。  
先让五只手单独可测，再挂进 Crew；先能审计「分析做没做」，再谈美化报告文风。
