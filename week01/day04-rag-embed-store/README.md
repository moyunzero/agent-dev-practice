# Week 1 / Day 4 — RAG 向量化与存储

> **状态**：`available`  
> **长文教程**（可选）：[理解 Embedding 并用 Chroma 构建本地向量索引](../../notes/week01/day04-rag-embed-store.md)

## 今日目标

理解 Embedding 与余弦相似度；用 sentence-transformers 向量化；Chroma 持久化入库；问句 Top-K 检索。

## 前置

- Day 3 的分块概念
- 首次 `uv sync` 会下载 Embedding 模型（约数分钟，~数百 MB）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/sample.md` | 与 Day 3 同主题的 MD 样例 |
| `step01_cosine_intuition.py` | **第 1 步**：余弦相似度直觉（小向量手算） |
| `step02_embed_texts.py` | **第 2 步**：`embed_query` / `embed_documents` 区别 |
| `demo_index_chunks.py` | **第 3 步**：切分 → embed → 写入 `chroma_db/` |
| `demo_search.py` | **第 4 步**：问句 Top-K，带 similarity score |
| `demo_rag_retrieve.py` | **第 5 步**：检索结果格式化为 RAG 上下文 |
| `main.py` | 可选 CLI 入口 |
| `chroma_db/` | 运行后生成的向量库（可删重建） |
| `pyproject.toml` / `uv.lock` | chromadb、sentence-transformers |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 安装依赖 + 首次可能下载模型 |
| 1 | `uv run python step01_cosine_intuition.py` | 相似度数值对比 |
| 2 | `uv run python step02_embed_texts.py` | 向量维度、单条 vs 批量 embed |
| 3 | `uv run python demo_index_chunks.py` | 入库 N 条 chunk |
| 4 | `uv run python demo_search.py` | 问句命中 Top-K + score |
| 5 | `uv run python demo_rag_retrieve.py` | 检索片段可拼进 prompt |

## 验收命令（汇总）

```bash
uv run python step01_cosine_intuition.py
uv run python step02_embed_texts.py
uv run python demo_index_chunks.py
uv run python demo_search.py
uv run python demo_rag_retrieve.py
```

## 验收标准

- 能说清 Embedding / Vector Store / Top-K
- Chroma 入库 4 条 chunk；问句 `chunk_overlap 是干什么的？` 检索 Top-2 合理
- 能串讲：load → split → embed → store → search

## 收工清理

```bash
rm -rf .venv __pycache__ chroma_db/
```
