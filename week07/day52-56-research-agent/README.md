# Week 7–8 / Day 52–56 — 项目二：自动化投研 Agent

> **状态**：`available`  
> **长文教程**：[用 CrewAI 搭自动化投研流水线：搜集 → 财报分析 → 撰写](../../notes/week07/day52-56-research-agent.md)

## 今日目标

完成需求分析、Agent 设计、工具开发和工作流实现：CrewAI 三人顺序流（搜集 / 财报分析 / 撰写）、≥5 工具、中间产出可审计、工具重试/降级；付费 API 可用 fixture 等价替代。

## 前置

- Python ≥3.10 + [uv](https://github.com/astral-sh/uv)  
- 本机 [Ollama](https://ollama.com/)（默认模型 `llama3.1:8b`，可用 `OLLAMA_MODEL` 覆盖）

## 文件说明

| 文件 | 作用 |
|------|------|
| `research_tools.py` | ≥5 工具（搜网/简介/SEC/指标/写文件）；默认读 `fixtures/` |
| `fixtures/` | Acme 演示数据（等价 Search / SEC） |
| `step01_tools_invoke.py` | 不经 Agent，直接 invoke 五工具 |
| `step02_research_crew.py` | 三人 sequential Crew + `intermediate/` 落盘 |
| `step03_retry_fallback.py` | tenacity 重试 + fixture 降级 |
| `pyproject.toml` | crewai + tenacity |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | `uv sync` | 装依赖 |
| 2 | `uv run python step01_tools_invoke.py` | 先测五只手 |
| 3 | `uv run python step02_research_crew.py` | 整条小队（需 Ollama） |
| 4 | `uv run python step03_retry_fallback.py` | 重试/降级 |
| 5 | `RETRY_ATTEMPTS=2 uv run python step03_retry_fallback.py` | 观察 A 段降级 |

## 验收命令（汇总）

```bash
cd week07/day52-56-research-agent
uv sync

uv run python step01_tools_invoke.py
# 期望：五段输出；output/acme_corp_report.md 存在

# 确认 Ollama：curl -s http://127.0.0.1:11434/api/tags
OTEL_SDK_DISABLED=true uv run python step02_research_crew.py
# 期望：搜集→分析→撰写；intermediate/ 下有 01_/02_/03_ 文件

uv run python step03_retry_fallback.py
RETRY_ATTEMPTS=2 uv run python step03_retry_fallback.py
# 期望：默认 A 段 [live]；ATTEMPTS=2 时 A 段 [fixture 降级]
```

**边界**：系统不荐股；fixture 非实时 SEC；小模型可能「演」工具调用而未真正写 `output/`——以 `intermediate/` 审计分析步是否完成。
