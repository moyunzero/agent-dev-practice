"""第 2 课：RAGAs 最小跑通 — 用 Ollama 当裁判，给固定样本打分。"""

from __future__ import annotations

import os
from datasets import Dataset
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AnswerRelevancy, Faithfulness
from ragas.run_config import RunConfig

# 避免 RAGAs 误走 OpenAI 默认路径（本地 Ollama 评测常见坑）
os.environ.setdefault("OPENAI_API_KEY", "local-not-used")

JUDGE_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# 来自第 1 课的场景 ①②③ — 人工写好 question / contexts / answer
SAMPLES = [
    {
        "question": "chunk_overlap 是干什么的？",
        "contexts": [
            "chunk_overlap 表示相邻两个 chunk 之间重叠的字符数，"
            "用于避免一句话被切到两段里，导致检索时丢失完整语义。"
        ],
        "answer": (
            "chunk_overlap 是相邻 chunk 之间重叠的字符数，"
            "用来避免句子被切断、检索时丢语义。"
        ),
        "ground_truth": "chunk_overlap 是相邻分块之间的重叠字符数，避免切断句子。",
    },
    {
        "question": "ERR_CHUNK_42 怎么处理？",
        "contexts": [
            "chunk_size 建议 200～500；chunk_overlap 建议 50～100。"
            "分块过大检索粒度粗，过小上下文碎片化。"
        ],
        "answer": (
            "ERR_CHUNK_42 表示向量索引与源文档不一致。"
            "应停止写入、清空旧 collection、重新 embed 全量 chunk 后再开放查询。"
        ),
        "ground_truth": "停止写入，清空 collection，重新 embed 全量 chunk。",
    },
    {
        "question": "chunk_overlap 是干什么的？",
        "contexts": [
            "chunk_overlap 表示相邻两个 chunk 之间重叠的字符数，"
            "用于避免一句话被切到两段里。"
        ],
        "answer": (
            "FastAPI 是一个用于构建 API 的 Python Web 框架，"
            "支持自动生成 OpenAPI 文档。"
        ),
        "ground_truth": "chunk_overlap 是相邻分块之间的重叠字符数。",
    },
]


def build_judge():
    llm = LangchainLLMWrapper(
        ChatOllama(
            model=JUDGE_MODEL,
            temperature=0,
            num_predict=1024,
            timeout=600,
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    )
    return llm, embeddings


def main() -> None:
    print(f"Judge LLM: Ollama/{JUDGE_MODEL}")
    print(f"Embeddings: {EMBED_MODEL}")
    print("评测样本数:", len(SAMPLES), "\n")

    dataset = Dataset.from_list(SAMPLES)
    llm, embeddings = build_judge()

    faithfulness = Faithfulness(llm=llm)
    answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)

    print("RAGAs 评估中（Judge 会逐条读 question / contexts / answer）...\n")
    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=600, max_workers=1),
    )

    df = result.to_pandas()
    print("=== 逐条分数 ===")
    for i, row in df.iterrows():
        print(f"[{i + 1}] {SAMPLES[i]['question'][:40]}...")
        print(f"    faithfulness      = {row['faithfulness']:.4f}")
        print(f"    answer_relevancy  = {row['answer_relevancy']:.4f}")
    print()
    print("=== 均值 ===")
    print(f"faithfulness      = {df['faithfulness'].mean():.4f}")
    print(f"answer_relevancy  = {df['answer_relevancy'].mean():.4f}")
    print(
        """
【本课要点】
1. RAGAs 输入列：question、contexts（列表）、answer；ground_truth 可选但建议有。
2. Judge 是另一个 LLM — 它读三元组打分，不是 BM25 那种公式。
3. 对比第 1 课直觉：样本 ② 应 faithfulness 偏低；样本 ③ 应 answer_relevancy 偏低。
4. 分数是 0～1，越高越好；小样本会有波动，看相对趋势比绝对值更重要。

下节课：把 Naive RAG 真实跑出来的 answer/contexts 喂进 RAGAs，对比优化链。
"""
    )


if __name__ == "__main__":
    main()
