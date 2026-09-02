# Week 3 / Day 21 — 研究助手（RAG + Web）

> **状态**：`available`  
> **长文教程**（可选）：[做一周收官的研究助手：RAG + Web 搜索](../../notes/week03/day21-research-assistant.md)

## 今日目标

集成本地 Nebula 笔记 RAG + DuckDuckGo Web 搜索；双工具 `create_agent` 研究助手。

## 前置

- Ollama（默认 `qwen2:7b`）
- 建索引需 Embedding 模型；Web 搜索需外网

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/nebula_notes.md` | 虚构内部笔记（知识库真相源） |
| `rag_store.py` | **模块**：加载笔记 → Chroma 索引 → 检索 |
| `research_tools.py` | **模块**：`search_knowledge_base` + `web_search` 两个 `@tool` |
| `step01_tools_alone.py` | **第 1 步**：不经过 Agent，单独测两个工具 |
| `demo_research_agent.py` | **第 2 步**：完整研究助手 Agent |
| `chroma_db/` | 运行后向量库（可删） |
| `pyproject.toml` / `uv.lock` | duckduckgo-search、chromadb |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 + 可能下载 embedding |
| 1 | `step01_tools_alone.py` | 知识库命中 N7-2026；Web 有摘要 |
| 2 | `demo_research_agent.py` | 内部题走 `search_knowledge_base` |
| 3 | 可选公网题 | 走 `web_search` |

## 验收命令（汇总）

```bash
cd week03/day21-research-assistant
uv sync
uv run python step01_tools_alone.py
uv run python demo_research_agent.py

# 可选：公网题
uv run python demo_research_agent.py "用网页搜索简要说明什么是 DuckDuckGo"
```

## 验收标准

- 问内部细节（桶数、N7-2026）时调用知识库工具
- Agent 答案与笔记内容一致

## 收工清理

```bash
rm -rf .venv chroma_db __pycache__
```
