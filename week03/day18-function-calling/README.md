# Week 3 / Day 18 — Function Calling

> **状态**：`available`  
> **长文教程**（可选）：[用 OpenAI API 做 Function Calling](../../notes/week03/day18-function-calling.md)

## 今日目标

理解 OpenAI 兼容 API 的 tools / tool_calls / role=tool 两轮协议；本地函数执行订单查询。

## 前置

- 默认 Ollama OpenAI 兼容 `/v1`（如 `qwen2:7b`）
- 或真 OpenAI：`OPENAI_API_KEY` + `OPENAI_MODEL`

## 文件说明

| 文件 | 作用 |
|------|------|
| `step01_fc_protocol.py` | **第 1 步**：打印 messages 结构；模拟 tool_calls 往返 |
| `demo_openai_fc_agent.py` | **第 2 步**：完整两轮 FC：模型点菜 → 本地 `get_order_status` → 模型总结 |
| `pyproject.toml` / `uv.lock` | openai SDK |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_fc_protocol.py` | JSON tools 定义与 message 角色 |
| 2 | `demo_openai_fc_agent.py` | 真实 API 调用 + 订单状态答案 |

## 验收命令（汇总）

```bash
cd week03/day18-function-calling
uv sync
uv run python step01_fc_protocol.py
uv run python demo_openai_fc_agent.py
```

## 验收标准

- 出现 `get_order_status` 的 tool_call
- 最终 Answer 引用订单状态字段

## 收工清理

```bash
rm -rf .venv __pycache__
```
