# Week 2 / Day 8 — Query Transformation

> **状态**：`available`  
> **长文教程**（可选）：[检索前先改写问句：Multi-Query 与 HyDE](../../notes/week02/day08-query-transform.md)

## 今日目标

在检索前改写问句：理解「检索鸿沟」；实现 Multi-Query、HyDE；对比 `none` / `multi_query` / `hyde` 对 RAG 召回的影响。

## 前置

- Week 1 Naive RAG 基础（Day 4–6）
- Ollama 已启动（默认 `qwen2:7b`）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/sample.md` | 假资料库（含故意难检索的表述） |
| `step01_retrieval_gap.py` | **第 1 步**：同一问句字面检索 vs 语义检索的鸿沟 |
| `demo_multi_query.py` | **第 2 步**：LLM 生成多条查询再检索 |
| `demo_hyde.py` | **第 3 步**：HyDE 假设文档嵌入检索 |
| `demo_rag_with_transform.py` | **第 4 步**：完整 RAG + `--mode none\|multi_query\|hyde` |
| `pyproject.toml` / `uv.lock` | LangChain + Chroma + Ollama |
| `.env.example` | 模型名等 |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` && `cp .env.example .env` | 环境就绪 |
| 1 | `uv run python step01_retrieval_gap.py` | 为何原问句召回差 |
| 2 | `uv run python demo_multi_query.py` | 多条 query 及合并召回 |
| 3 | `uv run python demo_hyde.py` | 假设答案 → 向量检索 |
| 4 | `demo_rag_with_transform.py --mode none` | 基线 RAG |
| 5 | `--mode multi_query` / `--mode hyde` | 对比最终 answer 与 sources |

## 验收命令（汇总）

```bash
cd week02/day08-query-transform
uv sync
cp .env.example .env

uv run python step01_retrieval_gap.py
uv run python demo_multi_query.py
uv run python demo_hyde.py
uv run python demo_rag_with_transform.py --mode none
uv run python demo_rag_with_transform.py --mode multi_query
uv run python demo_rag_with_transform.py --mode hyde
```

## 验收标准

- 能解释 Multi-Query / HyDE 各解决什么问题
- 三种 `--mode` 下 sources 或 answer 有明显差异
- 假资料库内容不被模型胡编为「事实来源」

## 收工清理

```bash
rm -rf .venv __pycache__ chroma_db/
```
