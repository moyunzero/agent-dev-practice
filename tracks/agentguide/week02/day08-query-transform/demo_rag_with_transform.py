"""第 4 课：把 Query Transformation 接到 RAG 链（可选 multi_query / hyde / none）。"""

from __future__ import annotations

import argparse

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from demo_hyde import hyde_retrieve
from demo_multi_query import multi_query_retrieve
from step01_retrieval_gap import build_vectorstore

TOP_K = 2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2:7b"


settings = Settings()


def make_llm(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.ollama_base_url,
        api_key="ollama",
        model=settings.ollama_model,
        temperature=temperature,
    )


def retrieve_context(store: Chroma, question: str, mode: str) -> tuple[str, str]:
    """返回 (context 文本, 调试说明)。"""
    if mode == "none":
        docs = store.similarity_search(question, k=TOP_K)
        ctx = "\n\n---\n\n".join(d.page_content for d in docs)
        return ctx, "模式=none（原问句直接检索）"

    if mode == "multi_query":
        ranked = multi_query_retrieve(store, question, n=3)
        # 只取最好的 TOP_K 段进 Prompt
        top = ranked[:TOP_K]
        ctx = "\n\n---\n\n".join(c for c, _ in top)
        return ctx, f"模式=multi_query（合并后取 Top-{TOP_K}）"

    if mode == "hyde":
        hypo, ranked = hyde_retrieve(store, question)
        # 生产常见做法：假段落检索 + 原问句检索 合并（简化：各取 1，再去重）
        raw = store.similarity_search_with_score(question, k=1)
        merged: dict[str, float] = {c: s for c, s in ranked}
        for doc, score in raw:
            key = doc.page_content
            if key not in merged or score < merged[key]:
                merged[key] = score
        top = sorted(merged.items(), key=lambda x: x[1])[:TOP_K]
        ctx = "\n\n---\n\n".join(c for c, _ in top)
        note = (
            "模式=hyde（假段落检索 ∪ 原问句检索）\n"
            f"--- 假设段落预览 ---\n{hypo[:200]}..."
        )
        return ctx, note

    raise ValueError(f"未知 mode: {mode}")


def answer_with_rag(store: Chroma, question: str, mode: str) -> None:
    context, debug = retrieve_context(store, question, mode)
    print(f"=== 检索调试 ===\n{debug}\n")
    print("=== 最终塞进 Prompt 的资料 ===")
    print(context[:400] + ("...\n" if len(context) > 400 else "\n"))

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是文档问答助手。只根据【资料】回答；资料未提及请说「资料未提及」。回答简洁。",
            ),
            ("human", "【资料】\n{context}\n\n【问题】\n{question}"),
        ]
    )
    answer = (prompt | make_llm(0) | StrOutputParser()).invoke(
        {"context": context, "question": question}
    )
    print("=== 模型回答 ===")
    print(answer)
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Day8 RAG + Query Transformation")
    parser.add_argument(
        "--mode",
        choices=["none", "multi_query", "hyde"],
        default="multi_query",
        help="检索前改写策略",
    )
    parser.add_argument(
        "--question",
        default="切文档时怎么让前后两段有一点重复，避免句子被切断？",
    )
    args = parser.parse_args()

    store = build_vectorstore()
    print(f"模型: {settings.ollama_model}")
    print(f"问句: {args.question}")
    print(f"mode: {args.mode}\n")
    answer_with_rag(store, args.question, args.mode)

    print(
        """【本课要点】
Query Transformation 只改「检索前」；最终回答仍必须基于真 chunk。
可对比三种模式：
  uv run python demo_rag_with_transform.py --mode none
  uv run python demo_rag_with_transform.py --mode multi_query
  uv run python demo_rag_with_transform.py --mode hyde
"""
    )


if __name__ == "__main__":
    main()
