"""第 1 课（上）：ReAct 循环 — Thought / Action / Observation vs 固定 RAG 链。"""

from __future__ import annotations

REACT_TRACE = """
用户: 北京今天比上海高几度？

Thought 1: 需要先查两城气温，再相减。
Action 1: get_weather(city="北京")
Observation 1: 北京 28°C

Thought 2: 还缺上海气温。
Action 2: get_weather(city="上海")
Observation 2: 上海 24°C

Thought 3: 28 - 24 = 4，可以回答。
Action 3: Finish
Answer: 北京今天比上海高约 4 度。
""".strip()


def main() -> None:
    print("=== Week1–2 RAG：固定流水线 ===")
    print("  问句 → [检索] → [拼 Prompt] → [LLM 一次生成]")
    print("  特点：步骤在代码里写死，LLM 只负责「读 context + 答」")
    print()
    print("=== Agent + ReAct：模型决定下一步 ===")
    print("  问句 → LLM 想(Thought) → 选工具(Action) → 看结果(Observation) → 循环…")
    print("  特点：缺信息时会自己调工具，而不是只靠预先检索到的 chunk")
    print()
    print("--- 手撕 ReAct 轨迹（论文里的三类标记）---")
    print(REACT_TRACE)
    print()
    print("对照 Day14：Hybrid+Rerank 仍是「检索一次 → 生成一次」；")
    print("ReAct Agent 可能在 Observation 后再次 Thought，多次 Action。")


if __name__ == "__main__":
    main()
