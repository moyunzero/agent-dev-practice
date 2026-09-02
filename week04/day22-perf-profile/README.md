# Week 4 / Day 22 — 性能瓶颈分析

> **状态**：`available`  
> **长文教程**（可选）：[用 cProfile 和 py-spy 分析现有 Agent 的性能瓶颈](../../notes/week04/day22-perf-profile.md)

## 今日目标

cProfile / py-spy 分析 Agent：小流水线热身 → 真实 Agent 画像；识别等模型 I/O 占主导。

## 前置

- `step01`–`step02` 可不依赖 Ollama
- `step03`/`step04` 需 Ollama
- macOS 上 py-spy 可能需要 `sudo`

## 文件说明

| 文件 | 作用 |
|------|------|
| `workload.py` | **模块**：CPU 密集 vs sleep 模拟 I/O 的小负载 |
| `step01_cprofile.py` | **第 1 步**：cProfile 打在小流水线上 |
| `step02_pyspy_target.py` | **第 2 步**：长时间 sleep 进程，供 py-spy attach |
| `real_agent.py` | **模块**：Day15 风格真实 Agent（调 Ollama） |
| `step03_cprofile_agent.py` | **第 3 步**：cProfile × 真实 Agent |
| `step04_pyspy_agent_target.py` | **第 4 步**：挂起 Agent 请求，供 py-spy top |
| `demo_pyspy_record.py` | 可选：录制 flamegraph SVG |
| `pyproject.toml` / `uv.lock` | py-spy（可选 dev） |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_cprofile.py` | 看懂 cumulative time 排序 |
| 2 | `step02_pyspy_target.py` + py-spy | 可选热身 |
| 3 | `step03_cprofile_agent.py` | **核心**：`socket.recv` 等占满 |
| 4 | 终端 A：`step04_pyspy_agent_target.py` | 打印 PID |
| 5 | 终端 B：`py-spy top --pid <PID>` | 看 httpcore/Ollama 栈 |

## 验收命令（汇总）

```bash
cd week04/day22-perf-profile
uv sync
uv run python step01_cprofile.py
uv run python step03_cprofile_agent.py

# 终端 A
uv run python step04_pyspy_agent_target.py
# 终端 B（macOS 或需 sudo）
uv run py-spy top --pid <数字>
```

## 验收标准

- 真实 Agent cProfile 热点在等模型 I/O，非 Python 计算
- py-spy 栈可见 HTTP/Ollama 相关帧

## 收工清理

```bash
rm -rf .venv __pycache__ profile.svg agent_profile.svg
```
