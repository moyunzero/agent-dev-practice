"""第 1 课：RAG 评估指标直觉 — Faithfulness / Answer Relevancy 量在问什么。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    contexts: list[str]
    answer: str
    faithfulness: str
    answer_relevancy: str
    bottleneck: str
    why: str


SCENARIOS: list[Scenario] = [
    Scenario(
        name="① 理想情况",
        question="chunk_overlap 是干什么的？",
        contexts=[
            "chunk_overlap 表示相邻两个 chunk 之间重叠的字符数，"
            "用于避免一句话被切到两段里，导致检索时丢失完整语义。"
        ],
        answer=(
            "chunk_overlap 是相邻 chunk 之间重叠的字符数，"
            "用来避免句子被切断、检索时丢语义。"
        ),
        faithfulness="高",
        answer_relevancy="高",
        bottleneck="无明显瓶颈",
        why="答案里的关键事实都能在 context 里找到；也正面回答了「干什么」。",
    ),
    Scenario(
        name="② 检索错了 → 幻觉",
        question="ERR_CHUNK_42 怎么处理？",
        contexts=[
            "chunk_size 建议 200～500；chunk_overlap 建议 50～100。"
            "分块过大检索粒度粗，过小上下文碎片化。"
        ],
        answer=(
            "ERR_CHUNK_42 表示向量索引与源文档不一致。"
            "应停止写入、清空旧 collection、重新 embed 全量 chunk 后再开放查询。"
        ),
        faithfulness="低",
        answer_relevancy="中～高",
        bottleneck="检索（Recall）",
        why=(
            "答案在讲错误码处理，但 context 只有分块参数 — 关键步骤是「编」出来的。"
            "问句相关，但依据不足 → Faithfulness 低。"
        ),
    ),
    Scenario(
        name="③ 资料对，但答非所问",
        question="chunk_overlap 是干什么的？",
        contexts=[
            "chunk_overlap 表示相邻两个 chunk 之间重叠的字符数，"
            "用于避免一句话被切到两段里。"
        ],
        answer=(
            "FastAPI 是一个用于构建 API 的 Python Web 框架，"
            "支持自动生成 OpenAPI 文档。"
        ),
        faithfulness="低～中",
        answer_relevancy="低",
        bottleneck="生成 / Prompt",
        why=(
            "context 里根本没有 FastAPI；答案可能来自模型常识而非资料。"
            "即便某句碰巧在 context 里，也没有回答 chunk_overlap → Answer Relevancy 低。"
        ),
    ),
    Scenario(
        name="④ 检索漏了要点",
        question="ERR_CHUNK_42 怎么处理？",
        contexts=[
            "ERR_CHUNK_42 在索引与源文档不一致时出现。"
            "处理时需要停止写入并重建索引。"
        ],
        answer=(
            "出现 ERR_CHUNK_42 时要停止写入并重建索引。"
            "另外还需清空旧 collection、重新 embed 全量 chunk。"
        ),
        faithfulness="低～中",
        answer_relevancy="高",
        bottleneck="检索（Recall）+ 生成",
        why=(
            "context 只提到「停止写入、重建」，没写「清空 collection、全量 embed」。"
            "答案后半句若无法从 context 支撑 → Faithfulness 被拉低。"
            "但答案方向仍对准问句 → Answer Relevancy 可以较高。"
        ),
    ),
]


def preview(text: str, n: int = 72) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= n else one_line[: n - 3] + "..."


def show(s: Scenario) -> None:
    print(f"{'=' * 60}")
    print(s.name)
    print(f"问句: {s.question}")
    print("检索到的 context:")
    for i, ctx in enumerate(s.contexts, 1):
        print(f"  [{i}] {preview(ctx)}")
    print(f"模型答案: {preview(s.answer)}")
    print()
    print(f"  Faithfulness（忠实度）     → 预期: {s.faithfulness}")
    print(f"  Answer Relevancy（相关性） → 预期: {s.answer_relevancy}")
    print(f"  优先怀疑环节               → {s.bottleneck}")
    print(f"  原因: {s.why}")
    print()


def main() -> None:
    print("RAG 评估第 1 课：先看 4 个「坏答案」长什么样\n")
    print(
        "读每个场景时先自己想：哪项指标会低？该怪检索还是生成？\n"
        "脚本会在每个场景末尾给出参考答案。\n"
    )

    for scenario in SCENARIOS:
        show(scenario)

    print(
        """【本课要点】
1. Faithfulness：答案陈述能否被 context 支撑？低 → 先查检索是否捞错/漏，再查生成是否瞎编。
2. Answer Relevancy：答案有没有正面回应问句？低 → 多为生成或问句理解问题。
3. 两个指标可以「一高一低」— 不能只看最终答案像不像人话。
4. Day8/Day9 的优化主要抬检索侧；RAGAs 用同一批问句量化「优化有没有用」。

下节课：用 RAGAs + Ollama 给真实 RAG 流水线打分。
"""
    )


if __name__ == "__main__":
    main()
