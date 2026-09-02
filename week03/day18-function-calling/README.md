# Week 3 / Day 18 — Function Calling

> **状态**：`available`
> 对外文章：[用 OpenAI API 做 Function Calling：让模型「点菜」，本地函数「炒菜」](../../notes/week03/day18-function-calling.md)

## 前置

- 默认 Ollama + 支持 tools 的模型（如 `qwen2:7b`）  
- 或真 OpenAI：`OPENAI_API_KEY` + `OPENAI_MODEL`

## 验收命令（全文）

```bash
cd week03/day18-function-calling

uv sync
uv run python step01_fc_protocol.py
uv run python demo_openai_fc_agent.py
```

**期望**：出现 `tool_calls` → 本地 `get_order_status` 返回 → Answer 引用状态字段。

## 脚本

| 脚本 | 用途 |
|------|------|
| `step01_fc_protocol.py` | tools / tool_calls 协议示意 |
| `demo_openai_fc_agent.py` | OpenAI SDK 两轮 FC Agent |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
