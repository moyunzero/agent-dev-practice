"""Day23 Lesson 3 — 同问句连跑两次，打印前后延迟对比（手撕：对比优化前后）。"""

from __future__ import annotations

from step02_agent_llm_cache import QUESTION, ask_with_cache, cache_key, r

key = cache_key(QUESTION)
print(f"PING={r.ping()}  key={key}")
print(f"问句: {QUESTION}")
# 先删 key，保证第 1 次一定是 miss，才能公平对比
deleted = r.delete(key)
print(f"已清空该 key（删 {deleted} 条），开始对比\n")

rows = []
for i in range(1, 3):
    answer, status, elapsed = ask_with_cache(QUESTION)
    rows.append((i, status, elapsed, answer[:80]))
    print(f"第{i}次  [{status}]  {elapsed:.3f}s  |  {answer[:80]}")

miss_t = next(t for _, s, t, _ in rows if s == "miss")
hit_t = next(t for _, s, t, _ in rows if s == "hit")

print("\n--- 对比（同问句：无缓存 vs 有缓存）---")
print(f"无缓存(miss) ≈ {miss_t:.2f}s")
print(f"有缓存(hit)  ≈ {hit_t:.3f}s")
if hit_t > 0:
    print(f"加速约 {miss_t / hit_t:.0f}x")
else:
    print("hit 亚毫秒级（打印为 0.000）；相对 miss 相当于跳过整次 LLM")
