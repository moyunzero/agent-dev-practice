# Week 3 / Day 19 — Agent Memory

> **状态**：`available`
> 对外文章：[给 Agent 加对话记忆：从 ConversationBufferMemory 到 checkpointer](../../notes/week03/day19-agent-memory.md)

## 前置

- Ollama（默认 `qwen2:7b`）  

## 验收命令（全文）

```bash
cd week03/day19-agent-memory

uv sync
uv run python step01_no_memory.py
uv run python demo_memory_agent.py
```

**期望**：无记忆第二问常忘名；同 `thread_id` 能记住；换 `thread_id` 不能。

## 脚本

| 脚本 | 用途 |
|------|------|
| `step01_no_memory.py` | 无 checkpointer 对照 |
| `demo_memory_agent.py` | InMemorySaver + thread_id |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
