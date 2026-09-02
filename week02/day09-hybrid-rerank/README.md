# Week 2 / Day 9 — 混合检索与 Rerank

> **状态**：`available`  
> **长文教程**（可选）：[BM25 + 向量混合检索与 Rerank](../../notes/week02/day09-hybrid-rerank.md)

## 今日目标

BM25 关键词检索 + 向量语义检索 + RRF 融合；CrossEncoder Rerank 精排；四档流水线对比。

## 前置

- Day 8 或等价检索基础
- 首次运行下载 Embedding + CrossEncoder（复用 `~/.cache/huggingface`）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/sample.md` | 含错误码、分块参数等易混段落 |
| `step01_keyword_vs_semantic.py` | **第 1 步**：纯关键词 vs 纯向量谁更准 |
| `demo_bm25.py` | **第 2 步**：BM25 Top-K |
| `demo_hybrid_rrf.py` | **第 3 步**：BM25 + 向量 → RRF 融合 |
| `demo_rerank.py` | **第 4 步**：CrossEncoder 对 (问, 文) 重打分 |
| `demo_pipeline_compare.py` | **第 5 步**：vector / bm25 / hybrid / hybrid+rerank 四档对照 |
| `pyproject.toml` / `uv.lock` | rank_bm25、sentence-transformers、chromadb |

## 推荐顺序

| 步骤 | 命令 | 关注什么 |
|:----:|------|----------|
| 0 | `uv sync` | 首次较慢 |
| 1 | `step01_keyword_vs_semantic.py` | 错误码问句：向量可能偏、BM25 可能准 |
| 2 | `demo_bm25.py` | 词频检索结果 |
| 3 | `demo_hybrid_rrf.py` | RRF 合并排名 |
| 4 | `demo_rerank.py` | 精排后 Top-1 变化 |
| 5 | `demo_pipeline_compare.py` | **核心验收**：四档 Top-1 对比 |

## 验收命令（汇总）

```bash
cd week02/day09-hybrid-rerank
uv sync

uv run python step01_keyword_vs_semantic.py
uv run python demo_bm25.py
uv run python demo_hybrid_rrf.py
uv run python demo_rerank.py
uv run python demo_pipeline_compare.py
```

**推荐问句**：`ERR_CHUNK_42 怎么处理？` — 仅向量 Top-1 常偏「分块参数」；Hybrid+Rerank 应命中错误码段。

## 验收标准

- 四档流水线均可运行并打印 Top-K
- 能口述 BM25 / 向量 / RRF / Rerank 各干什么

## 收工清理

```bash
rm -rf .venv __pycache__ chroma_db/
```
