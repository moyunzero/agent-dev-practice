# Week 3 / Day 20 — Agent 错误处理

> **状态**：`available`
> 对外文章：[给 Agent 工具加韧性：tenacity 重试 + 降级策略](../../notes/week03/day20-agent-error-handling.md)

## 前置

- 第 1–2 课不需要大模型；第 3 课需要 Ollama（默认 `qwen2:7b`）  
- 依赖含 `tenacity`

## 验收命令（全文）

```bash
cd week03/day20-agent-error-handling

uv sync
uv run python step01_flaky_no_retry.py
uv run python demo_tenacity_fallback.py
uv run python demo_agent_resilient.py
```

**期望**：无重试直接异常；有 tenacity 后第 3 次成功出实时价；彻底失败时出现「降级缓存价」；Agent 能答出价格。

## 脚本

| 脚本 | 用途 |
|------|------|
| `flaky_price.py` | 模拟抖动 API |
| `step01_flaky_no_retry.py` | 无重试对照 |
| `demo_tenacity_fallback.py` | tenacity + 降级 |
| `demo_agent_resilient.py` | 挂进 Agent |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
