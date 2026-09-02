# Week 4 / Day 26 — Embedding 与 Rerank 批处理

> **状态**：`available`  
> **长文教程**（可选）：[给 Embedding 和 Rerank 做批处理](../../notes/week04/day26-batching.md)

## 今日目标

理解批处理吞吐；`embed_documents` vs 逐条；CrossEncoder 一批 `predict`；万级用 `embed_chunked` 防 OOM。

## 前置

- `step01` 无需 GPU
- `step02`/`step03` 首次会下载 HF 模型

## 文件说明

| 文件 | 作用 |
|------|------|
| `step01_batch_intuition.py` | **第 1 步**：纯 Python 玩具，一批 vs 逐条墙钟 |
| `step02_embed_batch.py` | **第 2 步**：真实 Embedding 逐条 vs `embed_documents` |
| `step03_rerank_batch.py` | **第 3 步**：CrossEncoder 逐对 vs 一批 predict |
| `embed_chunked.py` | **参考**：万级文本分批 embed（非 step 必跑） |
| `pyproject.toml` / `uv.lock` | sentence-transformers |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_batch_intuition.py` | 批处理为何更快（摊薄固定开销） |
| 2 | `step02_embed_batch.py` | 条数够时 batch 吞吐更高 |
| 3 | `step03_rerank_batch.py` | rerank 一批 vs 循环 |

## 验收命令（汇总）

```bash
cd week04/day26-batching
uv sync
uv run python step01_batch_intuition.py
uv run python step02_embed_batch.py
uv run python step03_rerank_batch.py
```

## 验收标准

- 玩具脚本一批明显快于逐条
- 真模型在条数 ≥ 若干时 batch 吞吐更高
- 知道建库万级应读 `embed_chunked.py` 分批

## 收工清理

```bash
rm -rf .venv __pycache__
```
