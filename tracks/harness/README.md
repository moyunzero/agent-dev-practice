# Harness 轨（阶段②）— WorkBuddy 风格桌面 Agent 工程课

> **状态**：`in_progress`（s01–s04 `available`；后续章节按学会进度发布）  
> **轨登记**：[docs/TRACKS.md](../../docs/TRACKS.md) · **上游蓝图**：[learn-workbuddy](https://github.com/adongwanai/learn-workbuddy)

模型是大脑，Harness 是操作系统。本目录是本仓**可跑切片**：每章一个 `code.py`，默认离线 `--demo`。

教学长文在 [`notes/learn-workbuddy/`](../../notes/learn-workbuddy/)；上游完整 24 章与测试仍以 [learn-workbuddy](https://github.com/adongwanai/learn-workbuddy) 为准。本切片含运行 `--demo` 所需的 `mini_workbuddy` 辅助包，见 [NOTICE.md](./NOTICE.md)。

## 60 秒跑通

```bash
cd tracks/harness
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # 纯 --demo 可不填 Key
python3 s01_agent_loop/code.py --demo
```

## 章节索引

| 章 | 主题 | 状态 | 代码 | 长文 |
|----|------|:----:|------|------|
| s01 | Agent Loop | `available` | [s01_agent_loop](./s01_agent_loop/) | [notes](../../notes/learn-workbuddy/s01-agent-loop.md) |
| s02 | Tool Dispatch | `available` | [s02_tool_dispatch](./s02_tool_dispatch/) | [notes](../../notes/learn-workbuddy/s02-tool-dispatch.md) |
| s03 | Deferred Loading | `available` | [s03_deferred_loading](./s03_deferred_loading/) | [notes](../../notes/learn-workbuddy/s03-deferred-loading.md) |
| s04 | Permission & Hooks | `available` | [s04_permission_hooks](./s04_permission_hooks/) | [notes](../../notes/learn-workbuddy/s04-permission-hooks.md) |
| s05–s24 | 桌面运行时 → 综合 | `planned` | — | — |

## 目录说明

| 路径 | 作用 |
|------|------|
| `s0N_*/code.py` | 该章可跑教学脚本（支持 `--demo`） |
| `s0N_*/images/` | 章内架构图 |
| `mini_workbuddy/` | 共享 `--demo` / provider 入口（非产品源码） |
| `requirements.txt` | 教学依赖 |
| `.env.example` | Key / provider 模板 |

## 和阶段①的关系

先走完 [AgentGuide Day1–60](../agentguide/)（会用工具的 Agent / RAG），再来本轨看「桌面 Harness 怎么把工具调用变成可审批、可审计的执行」。
