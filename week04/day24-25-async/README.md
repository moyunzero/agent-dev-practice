# Week 4 / Day 24–25 — 异步处理

> **状态**：`available`  
> **长文教程**（可选）：[把 I/O 密集调用改成异步](../../notes/week04/day24-25-async.md)

## 今日目标

理解 sync vs async；`asyncio.gather` 并发 I/O；FastAPI `async def` + 反例 `time.sleep` 堵 loop。

## 前置

- 无需 Docker；模拟 I/O 用 `asyncio.sleep`

## 文件说明

| 文件 | 作用 |
|------|------|
| `step01_sync_vs_async.py` | **第 1 步**：同步串行 vs asyncio.gather 墙钟对比 |
| `step02_gather_api.py` | **第 2 步**：多个假 API 并发 gather |
| `main_api.py` | **第 3 步**：FastAPI `/async-ask`（真异步）vs `/async-block`（sleep 堵 loop） |
| `step03_bench_client.py` | **第 4 步**：并发 8 请求压客户端侧对比 |
| `pyproject.toml` / `uv.lock` | fastapi、httpx |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_sync_vs_async.py` | 建立直觉 |
| 2 | `step02_gather_api.py` | gather 模式 |
| 3 | 终端 1：`uvicorn main_api:app --port 8024` | 起服务 |
| 4 | 终端 2：`step03_bench_client.py` | **核心验收** |

## 验收命令（汇总）

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

## 验收标准

- `/async-ask` 并发总耗时 ≈ **0.4s** 量级
- `/async-block` 并发总耗时 ≈ **1.2s** 量级（明显更慢）

## 收工清理

```bash
# 停 uvicorn 后
rm -rf .venv __pycache__
```
