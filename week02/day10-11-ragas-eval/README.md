# Week 2 / Day 10–11 — RAG 评估（RAGAs）

> **状态**：`available`
> 对外文章：[用 RAGAs 评估 RAG](../../notes/week02/day10-11-ragas-eval.md)

## 怎么学

按文章自学或逐脚本跟练；不要一次跑完全部 demo。开工前先看 [对外文章](../../notes/week02/day10-11-ragas-eval.md) 中的上游目标。

## 验收命令

```bash
cd week02/day10-11-ragas-eval
uv sync

uv run python step01_metrics_intuition.py
uv run python demo_ragas_baseline.py

# 快速单问对比（不跑 RAGAs）
uv run python demo_eval_pipeline.py --mode hybrid_rerank --question "ERR_CHUNK_42 怎么处理？"
uv run python demo_eval_pipeline.py --mode naive --question "ERR_CHUNK_42 怎么处理？"

# 两档完整对比 + RAGAs（慢）
OLLAMA_MODEL=qwen2.5-coder:7b uv run python demo_eval_pipeline.py --compare
```

**需要**：本机 Ollama 已启动；Judge 推荐 `qwen2.5-coder:7b`。
