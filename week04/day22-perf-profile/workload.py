"""故意带瓶颈的「迷你 Agent 流水线」——供 cProfile / py-spy 分析。

阶段：retrieve（CPU 忙等）→ embed（sleep 模拟 I/O）→ llm（sleep 模拟推理）。
"""

from __future__ import annotations

import hashlib
import time


def fake_retrieve(query: str, *, rounds: int = 1_200_000) -> list[str]:
    """CPU 密集：反复哈希，模拟「慢检索 / 重计算」。"""
    h = query.encode()
    for i in range(rounds):
        h = hashlib.sha256(h + str(i).encode()).digest()
    return [f"doc:{query}", f"hash:{h.hex()[:16]}"]


def fake_embed(texts: list[str]) -> list[list[float]]:
    """模拟 Embedding HTTP / 模型加载等待（墙钟时间，CPU 不一定高）。"""
    time.sleep(0.25)
    return [[float(len(t)), 1.0] for t in texts]


def fake_llm(prompt: str) -> str:
    """模拟 LLM 推理等待。"""
    time.sleep(0.4)
    return f"Answer based on: {prompt[:48]}…"


def run_agent_pipeline(query: str) -> str:
    """一次「Agent」路径：检索 → 向量化 → 生成。"""
    docs = fake_retrieve(query)
    _vecs = fake_embed(docs)
    prompt = f"Q={query}\nCTX={docs[0]}"
    return fake_llm(prompt)
