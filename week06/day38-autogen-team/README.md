# Week 6 / Day 38 — AutoGen 实战：研究员–程序员–测试员

> **状态**：`available`  
> **前置**：Day 36–37（`AssistantAgent` / `RoundRobinGroupChat`）  
> **长文教程**（可选）：[用 AutoGen AgentChat 搭「研究员–程序员–测试员」三人协作小队](../../notes/week06/day38-autogen-team.md)

## 今日目标

实现一个「研究员–程序员–测试员」的 Multi-Agent 系统（现役 AgentChat + Ollama）。

## 前置

- Python 3.10+、uv  
- Ollama 已启动并已 pull 模型（默认 `llama3.1:8b`）  
- 建议已完成 Day36–37

## 文件说明

| 文件 | 作用 |
|------|------|
| `lesson01_roles.md` | 三人角色与协作流程 |
| `lesson02_run_team.md` / `step02_dev_team.py` | 三人轮转脚本 |
| `lesson_api_cheatsheet.md` | API 入参/出参/何时用 |
| `pyproject.toml` | `autogen-agentchat` + `autogen-ext[ollama]==0.7.5` |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | 读 `lesson01_roles.md` | 角色与轮转 |
| 2 | `uv sync` → `uv run python step02_dev_team.py` | 见三人交替 |

## 验收命令（汇总）

```bash
cd week06/day38-autogen-team
uv sync
uv run python step02_dev_team.py
```

**期望**：终端交替出现 `researcher` / `coder` / `tester`；因 `APPROVE` 或消息上限结束。
