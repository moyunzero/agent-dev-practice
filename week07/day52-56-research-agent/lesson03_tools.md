# Day52–56 Lesson 3 — 工具开发（KP3）

> 挂钩上游：**工具开发**；集成 Google Search, SEC API, 文件读写等至少 5 个工具  
> 付费 API 可用免费/fixture **等价替代**（须在 README 标明）

## 本课唯一新点

**工具** = Agent 可调用的「手」（函数）：输入公司名/路径 → 返回文本结果。  
三人分工不变；工具按职责挂给对应 Agent，不是三人共用一把万能锤。

| # | 工具名（本仓） | 等价上游 | 挂给谁 | 干什么 |
|---|---------------|----------|--------|--------|
| 1 | `web_search` | Google Search | 搜集 | 公开网页摘要+链接 |
| 2 | `company_overview` | 公司基本面 API | 搜集 | 简介/行业/交易所等 |
| 3 | `sec_filings_search` | SEC API | 财报分析 | 查近期申报/财报条目 |
| 4 | `parse_filing_metrics` | 解析 PDF 财报、算指标 | 财报分析 | 从文本/fixture 抽关键指标 |
| 5 | `write_report_file` | 文件读写 | 撰写 | 把报告写入 `output/` |
| （+） | `read_notes_file` | 文件读写 | 撰写或分析 | 读中间稿（可选第 6 个） |

本仓默认：**无 Key 时走 `fixtures/`**，有网络再试真实搜索——工具签名不变，只换实现体。

## CrewAI 挂载（对照官方）

- 自定义工具：`from crewai.tools import tool`，用 `@tool("名称")` 包一层函数  
- 挂到人：`Agent(..., tools=[web_search, company_overview, ...])`  
- 官方：[Create Custom Tools](https://docs.crewai.com/en/concepts/tools)

## 易混

| | Agent | 工具 |
|--|-------|------|
| 是谁 | 角色（想什么、写什么） | 手（查网、读文件、算数） |
| 没有工具时 | 只能瞎编或空转 | — |
| 没有 Agent 时 | — | 函数能跑，但没人编排顺序 |
