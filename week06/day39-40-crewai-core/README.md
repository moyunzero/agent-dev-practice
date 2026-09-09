# Week 6 / Day 39–40 — CrewAI 核心概念

> **状态**：`available`  
> **前置**：Day 36–38（Multi-Agent 直觉；本课换框架）  
> **长文教程**（可选）：[用 CrewAI 跑通 Agent / Task / Crew / Process 最小示例](../../notes/week06/day39-40-crewai-core.md)

## 今日目标

学习 Agent、Task、Crew、Process 的概念，并运行官方风格示例（Ollama）。

## 前置

- Python 3.10+、uv  
- Ollama 已启动并已 pull 模型（默认 `llama3.1:8b`）

## 文件说明

| 文件 | 作用 |
|------|------|
| `lesson01_crewai_map.md` | 四概念地图 |
| `lesson02_minimal_crew.md` / `step02_minimal_crew.py` | 最小 sequential Crew |
| `lesson_api_cheatsheet.md` | API 入参/出参/何时用 |
| `pyproject.toml` / `uv.lock` | `crewai[litellm]==1.15.20` |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | 读 `lesson01_crewai_map.md` | 四概念 |
| 2 | `uv sync` → `uv run python step02_minimal_crew.py` | kickoff |

## 验收命令（汇总）

```bash
cd week06/day39-40-crewai-core
uv sync
uv run python step02_minimal_crew.py
```

**期望**：先完成研究 Task，再完成写口号 Task；打印最终结果。
