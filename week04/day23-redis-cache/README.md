# Week 4 / Day 23 — Redis 缓存 LLM 响应

> **状态**：`available`  
> **长文教程**（可选）：[给 Agent 加 Redis 缓存](../../notes/week04/day23-redis-cache.md)

## 今日目标

Docker Redis；缓存 Agent **最终 LLM 回答**；同问句 miss → hit 延迟对比。

## 前置

- Docker Desktop
- Ollama（step02/03）

## 文件说明

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | Redis 服务（宿主机端口 **6389**） |
| `redis_config.py` | 连接 host/port、key 前缀 |
| `step01_redis_ping.py` | **第 1 步**：连通、set/get、TTL；跑两次看 MISS/HIT |
| `step02_agent_llm_cache.py` | **第 2 步**：Agent + 回答级缓存；第二次 ~0s |
| `step03_compare_latency.py` | **第 3 步**：DEL 缓存后对比 miss vs hit 耗时 |
| `pyproject.toml` / `uv.lock` | redis、langchain |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `docker compose up -d` | Redis 6389 |
| 1 | `uv sync` | 依赖 |
| 2 | `step01_redis_ping.py` ×2 | 第二次 HIT |
| 3 | `step02_agent_llm_cache.py` ×2 | 第二次 `[hit]` 跳过 Ollama |
| 4 | `step03_compare_latency.py` | 数字对比 |

## 验收命令（汇总）

```bash
cd week04/day23-redis-cache
docker compose up -d && docker compose ps
uv sync
uv run python step01_redis_ping.py
uv run python step02_agent_llm_cache.py
uv run python step03_compare_latency.py
```

## 验收标准

- 同问句第二次为 cache hit
- 能区分「检索缓存」与「最终回答缓存」（本日做后者）

## 收工清理

```bash
docker compose down
rm -rf .venv __pycache__
```
