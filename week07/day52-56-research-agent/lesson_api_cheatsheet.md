# Day52–56 — 本课 API 说明书（CrewAI tools · 对照官方）

权威：[Tools](https://docs.crewai.com/en/concepts/tools)

## `@tool` / `crewai.tools.tool`

| | |
|--|--|
| **干什么** | 把普通函数变成 Agent 可调用的工具 |
| **本课入参** | `@tool("显示名")`；函数参数即工具入参（如 `company: str`） |
| **出参** | 字符串（摘要 / JSON 文本 / 路径） |
| **何时用** | 需要查网、读文件、算指标等「手」的时候 |

## 直接调用（不经 Agent）

| | |
|--|--|
| **写法** | `web_search.run(query="...")` |
| **何时用** | Lesson 3 先测工具本身；Lesson 4 再 `Agent(tools=[...])` |

## `Agent(tools=[...])`

| | |
|--|--|
| **入参** | 工具对象列表；按职责拆分，不要三人共用万能列表 |
| **何时用** | 挂到搜集 / 财报分析 / 撰写 |

## `tenacity.@retry`（Day20 同款）

| | |
|--|--|
| **干什么** | 偶发异常时自动再试 |
| **本课入参** | `stop_after_attempt(n)`、`wait_fixed(...)`、`retry_if_exception_type(ConnectionError)` |
| **出参** | 成功则返回函数结果；耗尽且 `reraise=True` 则抛出 |
| **何时用** | 网络抖动；**耗尽后**在外层 `try/except` 里降级 fixture |
| **官方** | [tenacity](https://tenacity.readthedocs.io/) |

## `Task(context=[...])` + `Process.sequential`

| | |
|--|--|
| **干什么** | 工单按顺序执行；后一张可读前面 Task 的产出 |
| **本课入参** | `context=[research_task]` 或 `[research_task, analysis_task]` |
| **出参** | 各 Task 有 `.output`；`kickoff()` 多为最后一张结果 |
| **何时用** | 流水线交接；中间产出用 `.output` 落盘审计 |
| **官方** | [Tasks](https://docs.crewai.com/en/concepts/tasks) · [Processes](https://docs.crewai.com/en/concepts/processes) |
