# Week 4 / Day 23 — Redis 缓存 LLM 响应

> **状态**：`available`
> 对外文章：[给 Agent 加 Redis 缓存：别让相同问句重复问模型](../../notes/week04/day23-redis-cache.md)

## 怎么学

按文章自学，或逐脚本跟练。需要 Docker（Redis）与 Ollama。

## 验收命令

```bash
cd week04/day23-redis-cache
docker compose up -d && docker compose ps   # 映射 6389
uv sync
uv run python step01_redis_ping.py          # 跑两次：MISS → HIT
uv run python step02_agent_llm_cache.py     # 跑两次：miss 数十秒 → hit ~0s
uv run python step03_compare_latency.py     # 先 DEL 再对比
```

**期望**：同问句第二次为 hit；`pipeline` 语义上跳过 Agent/Ollama。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `step01_redis_ping.py` | Redis 连通、TTL、MISS/HIT |
| `step02_agent_llm_cache.py` | Agent + 缓存最终回答 |
| `step03_compare_latency.py` | 优化前后延迟对比 |
| `redis_config.py` | 主机端口（默认 6389） |

## 收工后清理

```bash
docker compose down
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
