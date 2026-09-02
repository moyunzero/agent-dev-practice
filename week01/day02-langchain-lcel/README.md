# Week 1 / Day 2 — LangChain 六大模块 + LCEL

> **状态**：`available`  
> **长文教程**（可选）：[理解六大模块并熟练 LCEL](../../notes/week01/day02-langchain-lcel.md)

## 今日目标

理解 LangChain 六大模块地图；手撕并熟练 `prompt | model | parser` 的 LCEL 链；可选用 FastAPI 暴露 `/chain`。

## 前置

- 完成 Day 1 或熟悉 FastAPI 基础
- Ollama 已启动（默认 `qwen2:7b`）

## 文件说明

| 文件 | 作用 |
|------|------|
| `demo_modules_map.py` | **第 1 步**：六大模块（Models/Prompts/Chains/Memory/Indexes/Agents）地图与关系 |
| `demo_lcel.py` | **第 2 步**：LCEL 链 `prompt \| model \| parser` 最小手撕 |
| `demo_memory.py` | **第 3 步**：Memory 概念最小示例（与无状态 LLM 对比） |
| `main.py` | **第 4 步（扩展）**：FastAPI `POST /chain` 暴露同一条 LCEL |
| `pyproject.toml` / `uv.lock` | LangChain、langchain-ollama 等依赖 |
| `.env.example` | 模型名、Ollama base_url 等 |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 安装依赖 |
| 1 | `cp .env.example .env` | 环境就绪 |
| 2 | `uv run python demo_modules_map.py` | 打印六大模块说明 |
| 3 | `uv run python demo_lcel.py` | LCEL 链输出回答 |
| 4 | `uv run python demo_memory.py` | 有/无 Memory 行为差异 |
| 5 | `uv run uvicorn main:app --reload --port 8001` | 起 HTTP 服务 |
| 6 | 下方 curl `/chain` | JSON 返回链的结果 |

## 验收命令

```bash
cp .env.example .env

uv run python demo_modules_map.py
uv run python demo_lcel.py
uv run python demo_memory.py

uv run uvicorn main:app --reload --port 8001
curl -sS http://127.0.0.1:8001/chain \
  -H 'Content-Type: application/json' \
  -d '{"question":"FastAPI 是什么？","provider":"ollama"}'
```

文档：http://127.0.0.1:8001/docs

## 验收标准

- 能口述六大模块各解决什么问题
- 能解释 LCEL 数据流：`question` → prompt → model → parser → 字符串
- `/chain` 返回合理回答

## 收工清理

```bash
rm -rf .venv __pycache__
```
