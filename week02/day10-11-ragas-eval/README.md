# Week 2 / Day 10–11 — RAG 评估（RAGAs）

> **状态**：`available`  
> **长文教程**（可选）：[用 RAGAs 评估 RAG](../../notes/week02/day10-11-ragas-eval.md)

## 今日目标

理解 Faithfulness、Answer Relevancy；用 RAGAs + Ollama Judge 评估 Naive vs Hybrid+Rerank。

## 前置

- Day 9 混合检索概念
- Ollama 已启动；Judge 推荐 `qwen2.5-coder:7b`（`OLLAMA_MODEL=...`）

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/sample.md` | 索引文档 |
| `data/eval_set.json` | 评估用问句与参考答案 |
| `step01_metrics_intuition.py` | **第 1 步**：指标直觉（不调 RAGAs） |
| `demo_ragas_baseline.py` | **第 2 步**：最小 RAGAs 单条评估 |
| `demo_ragas_compare.py` | 可选：多档对比（较慢） |
| `rag_store.py` | 共享：建 Chroma 索引、检索 |
| `eval_common.py` | 共享：Ollama Judge、RAG 模式枚举 |
| `eval_pipeline.py` | 评估流水线逻辑 |
| `demo_eval_pipeline.py` | **第 3 步**：CLI `--mode naive\|hybrid_rerank` / `--compare` |
| `pyproject.toml` / `uv.lock` | ragas、datasets 等 |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 0 | `uv sync` | 依赖较多，首次较慢 |
| 1 | `step01_metrics_intuition.py` | 先懂指标含义 |
| 2 | `demo_ragas_baseline.py` | 跑通一条 RAGAs |
| 3 | `demo_eval_pipeline.py --mode hybrid_rerank --question "..."` | 单问句、不跑完整 RAGAs（快） |
| 4 | 同上 `--mode naive` | 对比 Top-1 差异 |
| 5 | `demo_eval_pipeline.py --compare` | 完整 RAGAs 两档对比（**慢**，可选） |

## 验收命令（汇总）

```bash
cd week02/day10-11-ragas-eval
uv sync

uv run python step01_metrics_intuition.py
uv run python demo_ragas_baseline.py

uv run python demo_eval_pipeline.py --mode hybrid_rerank --question "ERR_CHUNK_42 怎么处理？"
uv run python demo_eval_pipeline.py --mode naive --question "ERR_CHUNK_42 怎么处理？"

# 完整对比（慢）
OLLAMA_MODEL=qwen2.5-coder:7b uv run python demo_eval_pipeline.py --compare
```

## 验收标准

- 能解释 Faithfulness / Answer Relevancy
- hybrid 与 naive 在同一问句上 Top-1 或指标有可解释差异

## 收工清理

```bash
rm -rf .venv __pycache__ chroma_db/
```
