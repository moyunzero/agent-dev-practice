# Week 3 / Day 19 — Agent Memory

> **状态**：`available`  
> **长文教程**（可选）：[给 Agent 加对话记忆](../../notes/week03/day19-agent-memory.md)

## 今日目标

对比无记忆 vs InMemorySaver + `thread_id`；理解 ConversationBufferMemory 与 checkpointer 概念对齐。

## 前置

- Ollama（默认 `qwen2:7b`）

## 文件说明

| 文件 | 作用 |
|------|------|
| `step01_no_memory.py` | **第 1 步**：无 checkpointer；第二问常「忘记」名字 |
| `demo_memory_agent.py` | **第 2 步**：同 `thread_id` 记住；换 id 则隔离 |
| `pyproject.toml` / `uv.lock` | langgraph checkpointer |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_no_memory.py` | 第二问答不出第一问的名字 |
| 2 | `demo_memory_agent.py` | 同 thread 连续对话能记住 |

## 验收命令（汇总）

```bash
cd week03/day19-agent-memory
uv sync
uv run python step01_no_memory.py
uv run python demo_memory_agent.py
```

## 验收标准

- 无记忆：第二问Forget 名字
- 有记忆：同 `thread_id` 能答出；换 `thread_id` 不能

## 收工清理

```bash
rm -rf .venv __pycache__
```
