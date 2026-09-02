# Week 5 / Day 29 — LangSmith 链路追踪

> **状态**：`available`  
> **长文教程**（可选）：[用 LangSmith 追踪 Agent 调用链](../../notes/week05/day29-tracing.md)

## 今日目标

将 **LangSmith** 集成到研究助手 Agent（Day21），在 LangSmith UI 分析一次问答的调用链与延迟。

## 前置

- [LangSmith](https://smith.langchain.com/) 账号与 `LANGCHAIN_API_KEY`
- Ollama + `qwen2:7b`（与 Day21 一致）
- Day21 知识库已索引（首次跑 Day21 会自动建索引）

## 文件说明

| 文件 | 作用 |
|------|------|
| `.env.example` | LangSmith 环境变量模板；复制为 `.env` 并填 Key |
| `run_traced_research.sh` | 加载 `.env`，切到 Day21 目录跑 `demo_research_agent.py` |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 0 | `ollama list` | 确认模型可用 |
| 1 | `cp .env.example .env` | 填入真实 `LANGCHAIN_API_KEY` |
| 2 | `./run_traced_research.sh` | 默认问题跑研究助手 |
| 3 | 打开 LangSmith → Projects → `day29-research-assistant` | 查看最新 Trace 树 |

## 验收命令（汇总）

```bash
cd week05/day29-tracing
cp .env.example .env
# 编辑 .env：LANGCHAIN_API_KEY=lsv2_pt_...

chmod +x run_traced_research.sh
./run_traced_research.sh

# 可选自定义问题：
./run_traced_research.sh "Nebula Router 的内部协议版本和桶数分别是什么？"
```

**期望结果**

1. 终端 Agent 跑完（可能因 Ollama tool 格式报 tool 错，不影响 trace 上报）
2. LangSmith 对应 Project 出现新 Run
3. Trace 树可见模型 Run、tool Run（成功或 validation error）及各自 Duration

## 关闭追踪

`.env` 中设 `LANGCHAIN_TRACING_V2=false` 或 unset 相关变量后重跑即可。
