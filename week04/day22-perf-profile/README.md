# Week 4 / Day 22 — 性能瓶颈分析

> **状态**：`available`
> 对外文章：[用 cProfile 和 py-spy 分析现有 Agent 的性能瓶颈](../../notes/week04/day22-perf-profile.md)  

## 前置

- Ollama（step03/04）；热身 step01 可不依赖模型  

## 验收命令（全文）

```bash
cd week04/day22-perf-profile

uv sync
uv run python step01_cprofile.py
uv run python step03_cprofile_agent.py
# 终端 A：
uv run python step04_pyspy_agent_target.py
# 终端 B（换成真实 PID；macOS 或需 sudo）：
# uv run py-spy top --pid <数字>
```

**期望**：真实 Agent 的 cProfile 常见 `socket.recv`；py-spy 常见 http/Ollama 等待栈。

## 脚本

| 脚本 | 用途 |
|------|------|
| `workload.py` / `step01` / `step02` | 热身 |
| `real_agent.py` | 真实 Agent |
| `step03_cprofile_agent.py` | cProfile × Agent |
| `step04_pyspy_agent_target.py` | py-spy 目标 |

## 收工后清理

```bash
rm -rf .venv __pycache__ profile.svg agent_profile.svg
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
