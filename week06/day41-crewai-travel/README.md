# Week 6 / Day 41 — CrewAI 实战：旅行规划师–本地向导–预订专员

> **状态**：`available`  
> **前置**：Day 39–40（Agent / Task / Crew / Process）  
> **长文教程**（可选）：[用 CrewAI 搭「旅行规划师–本地向导–预订专员」三人小队](../../notes/week06/day41-crewai-travel.md)

## 今日目标

实现一个「旅行规划师–本地向导–预订专员」的 Multi-Agent 系统（CrewAI + Ollama）。

## 前置

- Python 3.10+、uv  
- Ollama 已启动并已 pull 模型（默认 `llama3.1:8b`）  
- 建议已完成 Day39–40

## 文件说明

| 文件 | 作用 |
|------|------|
| `lesson01_roles.md` | 三人角色与 Task 接力 |
| `lesson02_travel_crew.md` / `step02_travel_crew.py` | 三人 sequential Crew |
| `lesson_api_cheatsheet.md` | API 入参/出参/何时用 |
| `pyproject.toml` / `uv.lock` | `crewai[litellm]==1.15.20` |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | 读 `lesson01_roles.md` | 角色与顺序 |
| 2 | `uv sync` → `uv run python step02_travel_crew.py` | planner → guide → booker |

## 验收命令（汇总）

```bash
cd week06/day41-crewai-travel
uv sync
uv run python step02_travel_crew.py
```

**期望**：日志先后出现规划师、向导、预订专员；最终为建议预订（非真订单）。
