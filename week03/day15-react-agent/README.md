# Week 3 / Day 15 — Agent 核心概念（ReAct）

> **状态**：`available`  
> **长文教程**（可选）：[理解 ReAct：用 LangChain create_agent 跑通第一个带工具的 Agent](../../notes/week03/day15-react-agent.md)

## 今日目标

理解 ReAct（Thought / Action / Observation）；工具 schema；用 LangChain `create_agent` + `@tool` + Ollama 跑通带工具 Agent。

## 前置

- Ollama（默认 `qwen2:7b`，可 `OLLAMA_MODEL=...`）
- 无需 Docker

## 文件说明

| 文件 | 作用 |
|------|------|
| `step01_react_loop.py` | **第 1 步**：固定 RAG vs ReAct 对照；手撕 Thought/Action/Observation 打印 |
| `demo_tool_schema.py` | **第 2 步**：`@tool` 的 name / description / 参数 JSON schema |
| `demo_langchain_agent.py` | **第 3 步**：`create_agent` + 两个玩具工具（字数、加法）+ Ollama |
| `pyproject.toml` / `uv.lock` | langchain、langchain-ollama、langgraph |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 安装 langgraph 等 |
| 1 | `step01_react_loop.py` | ReAct 轨迹逐步打印 |
| 2 | `demo_tool_schema.py` | 工具「说明书」长什么样 |
| 3 | `demo_langchain_agent.py` | 完整 Agent 多轮工具调用 |

## 验收命令（汇总）

```bash
cd week03/day15-react-agent
uv sync
uv run python step01_react_loop.py
uv run python demo_tool_schema.py
uv run python demo_langchain_agent.py
```

## 验收标准

默认问句「单词 agent 有几个字母？把结果加10」：

- 先 `get_word_length` → Observation `5`
- 再 `add(5, 10)` → 最终答案 **15**

## 收工清理

```bash
rm -rf .venv __pycache__
```
