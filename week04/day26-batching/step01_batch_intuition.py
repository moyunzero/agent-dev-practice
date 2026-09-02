"""Day26 Lesson 1 — 批处理直觉：逐条「假装 embed」vs 一批处理。

不调真模型：每条固定开销 + 可变算力，看批量如何摊薄固定开销。
"""

from __future__ import annotations

import time


def fake_embed_one(text: str) -> int:
    """假装：每次调用有固定开销（像建连/启动），再按长度「算」。"""
    time.sleep(0.05)  # 固定开销
    return len(text)


def fake_embed_batch(texts: list[str]) -> list[int]:
    """假装：整批只付一次固定开销，再一口气算完。"""
    time.sleep(0.05)  # 整批只一次
    return [len(t) for t in texts]


def main() -> None:
    docs = [f"doc-{i}-" + ("x" * (i % 20)) for i in range(20)]

    t0 = time.perf_counter()
    one_by_one = [fake_embed_one(t) for t in docs]
    t_serial = time.perf_counter() - t0

    t0 = time.perf_counter()
    batched = fake_embed_batch(docs)
    t_batch = time.perf_counter() - t0

    assert one_by_one == batched
    print(f"文档数: {len(docs)}")
    print(f"逐条调用: {t_serial:.2f}s  （约 20×0.05 固定开销）")
    print(f"批处理  : {t_batch:.2f}s  （约 1×0.05 固定开销）")
    print(f"吞吐提升约: {t_serial / t_batch:.1f}x（本玩具模型）")


if __name__ == "__main__":
    main()
