"""Day23 Lesson 2 — 最小 Agent（同 Day22 结构）+ Redis 缓存 LLM 最终回答。

来源对照：week04/day22-perf-profile/real_agent.py（create_agent + 工具 + Ollama）
"""

from __future__ import annotations

import hashlib
import os
import time

import redis
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage

from redis_config import REDIS_HOST, REDIS_PORT

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
QUESTION = os.getenv(
    "QUESTION",
    "单词 agent 有几个字母？把结果加10",
)

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def cache_key(question: str) -> str:
    """同一问句 → 同一钥匙；改一个字 key 就变。"""
    digest = hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:16]
    return f"day23:llm:{digest}"


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def build_agent():
    return create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[get_word_length, add],
        system_prompt=(
            "你是严谨的助手。需要长度或加法时必须调用工具，禁止心算。"
            "先 get_word_length，再用返回的整数调用 add。"
        ),
    )


def run_agent(question: str) -> str:
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return "(no final answer)"


def ask_with_cache(question: str) -> tuple[str, str, float]:
    """返回 (answer, hit|miss, 秒)。"""
    key = cache_key(question)
    t0 = time.perf_counter()
    cached = r.get(key)
    if cached is not None:
        return cached, "hit", time.perf_counter() - t0

    answer = run_agent(question)
    r.set(key, answer, ex=CACHE_TTL)
    return answer, "miss", time.perf_counter() - t0


def main() -> None:
    print(f"Redis {REDIS_HOST}:{REDIS_PORT}  PING={r.ping()}")
    print(f"问句: {QUESTION}")
    print(f"key : {cache_key(QUESTION)}")

    answer, status, elapsed = ask_with_cache(QUESTION)
    print(f"[{status}] {elapsed:.2f}s")
    print(f"回答: {answer[:200]}")


if __name__ == "__main__":
    main()
