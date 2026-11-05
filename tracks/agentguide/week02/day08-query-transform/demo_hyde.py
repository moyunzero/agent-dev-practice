"""第 3 课：HyDE — 先让 LLM 写「假设资料段落」，再用该段落去向量检索。"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from step01_retrieval_gap import build_vectorstore

TOP_K = 2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2:7b"


settings = Settings()


def make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.ollama_base_url,
        api_key="ollama",
        model=settings.ollama_model,
        temperature=0.4,
    )


def make_hypothetical_document(question: str) -> str:
    """HyDE 核心：不直接答用户，而是写一段「看起来像资料」的假段落。"""
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是技术文档作者。根据用户问题，写一段 80～150 字的「假设资料段落」。\n"
                "要求：\n"
                "1. 写成笔记/文档口吻，不要写成「答案是…」\n"
                "2. 尽量包含该领域可能出现的术语（即使你不确定也要按常见写法）\n"
                "3. 只输出段落正文，不要标题、不要解释",
            ),
            ("human", "{question}"),
        ]
    )
    return (prompt | make_llm() | StrOutputParser()).invoke({"question": question})


def hyde_retrieve(store: Chroma, question: str) -> tuple[str, list[tuple[str, float]]]:
    hypo = make_hypothetical_document(question)
    # 关键：用「假设段落」做检索 query，而不是用原问句
    hits = store.similarity_search_with_score(hypo, k=TOP_K)
    ranked = [(doc.page_content, score) for doc, score in hits]
    return hypo, ranked


def main() -> None:
    store = build_vectorstore()
    question = "切文档时怎么让前后两段有一点重复，避免句子被切断？"

    print(f"模型: {settings.ollama_model}")
    print(f"原始问句: {question}\n")

    raw_doc, raw_score = store.similarity_search_with_score(question, k=1)[0]
    print("=== 对照 · 原问句直接检索 Top-1 ===")
    print(f"  score={raw_score:.4f}")
    print(f"  预览: {raw_doc.page_content.replace(chr(10), ' ')[:90]}...\n")

    hypo, ranked = hyde_retrieve(store, question)
    print("=== HyDE 生成的「假设资料段落」===")
    print(hypo)
    print()

    print("=== 用假设段落去检索 Top-K ===")
    for i, (content, score) in enumerate(ranked, 1):
        preview = content.replace("\n", " ")[:90]
        hit = "chunk_overlap" in content.lower() or "重叠" in content
        print(f"  [{i}] score={score:.4f}  分块参数段={'是' if hit else '否'}")
        print(f"      {preview}...\n")

    print(
        """【本课要点】
1. HyDE：问句 → LLM 写「假资料」→ 用假资料的向量去搜真文档。
2. 假资料不是最终答案；真正给用户的答案仍应基于检索到的真 chunk。
3. 若假资料写错方向，检索会偏；所以生产里常与原问句检索结果合并。
下节课：把 Multi-Query / HyDE 接到一条可跑的 RAG 链。
"""
    )


if __name__ == "__main__":
    main()
