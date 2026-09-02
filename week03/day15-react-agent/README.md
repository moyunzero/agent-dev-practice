# Week 3 / Day 15 — Agent 核心概念（ReAct）

> **状态**：`available`
> 对外文章：[理解 ReAct：用 LangChain create_agent 跑通第一个带工具的 Agent](../../notes/week03/day15-react-agent.md)

## 前置

- 本机 [Ollama](https://ollama.com/) 已拉模型，默认 `qwen2:7b`（可 `OLLAMA_MODEL=...` 覆盖）
- 无需 Docker
- 依赖含 `langchain` + `langchain-ollama` + `langgraph`（见 `pyproject.toml`）

## 验收命令（全文）

```bash
cd week03/day15-react-agent

uv sync
uv run python step01_react_loop.py
uv run python demo_tool_schema.py
uv run python demo_langchain_agent.py
```

**期望**：

- `step01`：RAG vs ReAct 对照 + 手撕 Thought/Action/Observation 轨迹  
- `demo_tool_schema`：打印工具名 / description / 参数类型  
- `demo_langchain_agent`：先 `get_word_length("agent")` → Observation `5`，再 `add(5, 10)` → `15`

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `step01_react_loop.py` | ReAct Thought/Action/Observation；对比固定 RAG 链 |
| `demo_tool_schema.py` | 打印工具 schema；docstring → 说明书 |
| `demo_langchain_agent.py` | LangChain `create_agent` + `@tool` + Ollama |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
