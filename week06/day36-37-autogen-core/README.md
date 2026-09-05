# Week 6 / Day 36–37 — AutoGen 核心概念（现役 AgentChat）

> **状态**：`available`  
> **长文教程**（可选）：[用现役 AutoGen AgentChat 跑通可对话 Agent 与轮转群聊](../../notes/week06/day36-37-autogen-core.md)

## 今日目标

学习 AutoGen 核心概念（上游：`ConversableAgent` / `GroupChat`），并运行官方风格示例。  
落地：**AgentChat 0.7.x**（`AssistantAgent` + `RoundRobinGroupChat`）+ Ollama。

## 前置

- Python 3.10+、uv  
- Ollama 已启动并已 pull 模型（默认 `llama3.1:8b`）

## 文件说明

| 文件 | 作用 |
|------|------|
| `lesson01_autogen_map.md` | 旧名→现役映射 |
| `lesson02_assistant_hello.md` / `step02_assistant_hello.py` | 单助手 |
| `lesson03_roundrobin.md` / `step03_roundrobin_two_agents.py` | 轮转双助手 |
| `lesson_api_cheatsheet.md` | API 入参/出参/何时用（官方依据） |
| `pyproject.toml` / `uv.lock` | `autogen-agentchat` + `autogen-ext[ollama]==0.7.5` |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | 读 lesson01 + API 说明书 | 映射与官方口径 |
| 2 | `uv run python step02_assistant_hello.py` | 单 Agent |
| 3 | `uv run python step03_roundrobin_two_agents.py` | RoundRobin |

## 验收命令（汇总）

```bash
cd week06/day36-37-autogen-core
uv sync
uv run python step02_assistant_hello.py
uv run python step03_roundrobin_two_agents.py
```

**期望**：单助手打出中文一句；双助手终端出现 `writer`/`critic` 交替，并因 APPROVE 或消息上限结束。

## 官方文档

- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/  
- https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html  
