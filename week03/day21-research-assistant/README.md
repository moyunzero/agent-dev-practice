# Week 3 / Day 21 — 研究助手（RAG + Web）

> **状态**：`available`
> 对外文章：[做一周收官的研究助手：把 RAG 和 Web 搜索都挂进同一个 Agent](../../notes/week03/day21-research-assistant.md)

## 前置

- Ollama（默认 `qwen2:7b`）  
- 建索引会拉 embedding 模型；网页搜索需要外网  

## 验收命令（全文）

```bash
cd week03/day21-research-assistant

uv sync
uv run python step01_tools_alone.py
uv run python demo_research_agent.py
# 可选：公网题
uv run python demo_research_agent.py "用网页搜索简要说明什么是 DuckDuckGo"
```

**期望**：知识库命中 N7-2026 / 桶数等；Agent 问内部细节时调用 `search_knowledge_base`。

## 脚本

| 脚本 | 用途 |
|------|------|
| `data/nebula_notes.md` | 本地私有笔记 |
| `rag_store.py` | Chroma 索引 / 检索 |
| `research_tools.py` | 两个 `@tool` |
| `step01_tools_alone.py` | 不经 Agent 测工具 |
| `demo_research_agent.py` | 双工具研究助手 |

## 收工后清理

```bash
rm -rf .venv chroma_db __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
