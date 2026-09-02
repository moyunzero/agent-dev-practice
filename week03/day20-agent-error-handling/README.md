# Week 3 / Day 20 — Agent 错误处理

> **状态**：`available`  
> **长文教程**（可选）：[给 Agent 工具加韧性：tenacity 重试 + 降级策略](../../notes/week03/day20-agent-error-handling.md)

## 今日目标

模拟抖动 API；无重试 vs tenacity 重试 + 降级缓存；挂进 Agent。

## 前置

- 第 1–2 课无需 LLM；第 3 课需 Ollama

## 文件说明

| 文件 | 作用 |
|------|------|
| `flaky_price.py` | **模块**：随机失败的价格 API（供各 demo import） |
| `step01_flaky_no_retry.py` | **第 1 步**：无重试，第一次就异常 |
| `demo_tenacity_fallback.py` | **第 2 步**：`@retry` + 彻底失败时返回降级缓存价 |
| `demo_agent_resilient.py` | **第 3 步**： resilient 工具挂进 `create_agent` |
| `pyproject.toml` / `uv.lock` | tenacity、langchain |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_flaky_no_retry.py` | 异常退出 |
| 2 | `demo_tenacity_fallback.py` | 第 3 次成功或降级文案 |
| 3 | `demo_agent_resilient.py` | Agent 能答出价格 |

## 验收命令（汇总）

```bash
cd week03/day20-agent-error-handling
uv sync
uv run python step01_flaky_no_retry.py
uv run python demo_tenacity_fallback.py
uv run python demo_agent_resilient.py
```

## 验收标准

- 无重试：第一次失败
- tenacity：`stop=3` 时可得实时价；更早 stop 走「降级缓存价」
- Agent 最终能输出价格

## 收工清理

```bash
rm -rf .venv __pycache__
```
