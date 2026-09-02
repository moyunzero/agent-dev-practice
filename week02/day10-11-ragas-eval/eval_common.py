"""评测共用：Judge 配置 + RAGAs evaluate 封装。"""

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

os.environ.setdefault("OPENAI_API_KEY", "local-not-used")

JUDGE_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def build_judge():
    llm = LangchainLLMWrapper(
        ChatOllama(
            model=JUDGE_MODEL,
            temperature=0,
            num_predict=4096,
            timeout=600,
            format="json",
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    )
    return llm, embeddings


def run_ragas_eval(rows: list[dict]) -> dict[str, float]:
    """rows: question, contexts, answer, ground_truth"""
    dataset = Dataset.from_list(rows)
    llm, embeddings = build_judge()

    faithfulness = Faithfulness(llm=llm)
    answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=600, max_workers=1),
        show_progress=True,
    )
    df = result.to_pandas()
    faith = df["faithfulness"].mean(skipna=True)
    ar = df["answer_relevancy"].mean(skipna=True)
    failed_f = int(df["faithfulness"].isna().sum())
    return {
        "faithfulness": float(faith) if faith == faith else float("nan"),
        "answer_relevancy": float(ar) if ar == ar else float("nan"),
        "faithfulness_failed": failed_f,
        "df": df,
    }
