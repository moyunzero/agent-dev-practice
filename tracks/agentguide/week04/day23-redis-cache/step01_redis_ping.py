"""Day23 Lesson 1 — 连通 Redis，演示 SET / GET / TTL / 命中。"""

from __future__ import annotations

import time

import redis

from redis_config import REDIS_HOST, REDIS_PORT

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

print(f"连 {REDIS_HOST}:{REDIS_PORT}")
print("PING ->", r.ping())

key = "day23:demo:llm:what-is-redis"
value = "Redis 是内存里的键值缓存，常用来记住 LLM 的完整回答。"

# 模拟「第一次」：未命中 → 假装调 LLM（sleep）→ 写入缓存，TTL 60 秒
cached = r.get(key)
if cached is None:
    print("MISS：缓存没有，假装调用 LLM…")
    time.sleep(0.5)
    r.set(key, value, ex=60)  # ex=秒，等价于带 TTL 的写入
    print("已写入 Redis，TTL=60s")
else:
    print("HIT：直接读缓存，不调 LLM")
    print("  value =", cached)

# 立刻再读一次 → 应命中
print("再 GET ->", r.get(key))
print("剩余 TTL(秒) ->", r.ttl(key))
