# Week 4 / Day 24–25 — 异步处理

> **状态**：`available`
> 对外文章：[把 I/O 密集调用改成异步：提升并发吞吐（附 LLM 优化手段地图）](../../notes/week04/day24-25-async.md)

## 验收命令

```bash
cd week04/day24-25-async
uv sync
uv run python step01_sync_vs_async.py
uv run python step02_gather_api.py

# 终端 1
uv run uvicorn main_api:app --port 8024
# 终端 2
uv run python step03_bench_client.py
```

**期望**：`/async-ask` 并发 ≈0.4s；`/async-block` ≈1.2s。

## 收工清理

```bash
# 停掉 uvicorn 后：
rm -rf .venv __pycache__
```
