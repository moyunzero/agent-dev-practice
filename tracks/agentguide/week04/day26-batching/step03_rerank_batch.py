"""Day26 Lesson 3 — Reranker：逐对 predict vs 一批 predict。"""

from __future__ import annotations

import os
import time

from sentence_transformers import CrossEncoder

MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
N = int(os.getenv("N_PAIRS", "24"))

query = "What is batching in embeddings?"
# 同一 query，多条候选文档 → 典型 rerank 输入
pairs = [(query, f"Candidate document about topic {i}.") for i in range(N)]


def main() -> None:
    model = CrossEncoder(MODEL)
    # 暖机
    _ = model.predict([pairs[0]])

    t0 = time.perf_counter()
    # CrossEncoder.predict 要的是配对列表；逐对也传 [p]。
    # 循环里每次新建一元列表会多一点 Python 开销，基准略偏「逐对更慢」，结论通常不变。
    one = [float(model.predict([p])[0]) for p in pairs]
    t_one = time.perf_counter() - t0

    t0 = time.perf_counter()
    batch = [float(x) for x in model.predict(pairs)]
    t_batch = time.perf_counter() - t0

    assert len(one) == len(batch) == N
    print(f"model={MODEL}  pairs={N}")
    print(f"逐对 predict ×{N}: {t_one:.2f}s  ({N / t_one:.1f} pairs/s)")
    print(f"一批 predict     : {t_batch:.2f}s  ({N / t_batch:.1f} pairs/s)")
    if t_batch > 0:
        print(f"批处理更快约: {t_one / t_batch:.1f}x")
    print(f"分数样例(批) top3 idx: {sorted(range(N), key=lambda i: batch[i], reverse=True)[:3]}")


if __name__ == "__main__":
    main()
