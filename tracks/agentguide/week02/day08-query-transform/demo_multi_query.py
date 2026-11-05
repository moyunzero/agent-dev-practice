"""第 2 课：Multi-Query — 1 个问句 → LLM 生成多条检索 query → 分别搜 → 合并去重。"""

from __future__ import annotations

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict

from step01_retrieval_gap import build_vectorstore

TOP_K_PER_QUERY = 2


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
        temperature=0.3,
    )


def expand_queries(question: str, n: int = 3) -> list[str]:
    """用 LLM 把 1 个问句改写成 n 条「适合检索」的问句。"""
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是检索助手。根据用户问题，生成 {n} 条不同表述的检索问句。"
                "要求：\n"
                "1. 每条单独一行，不要编号、不要解释\n"
                "2. 覆盖同义说法、关键词、口语与术语\n"
                "3. 只输出问句本身",
            ),
            ("human", "{question}"),
        ]
    )
    text = (prompt | make_llm() | StrOutputParser()).invoke({"question": question, "n": n})
    lines = [ln.strip().lstrip("0123456789.-、) ").strip() for ln in text.splitlines()]
    queries = [ln for ln in lines if ln]
    # 原问句也保留，避免改写跑偏时丢意图
    if question not in queries:
        queries.insert(0, question)
    return queries[: n + 1]


def multi_query_retrieve(store: Chroma, question: str, n: int = 3) -> list[tuple[str, float]]:
    """多路检索 + 按内容去重，保留最好（最小）score。"""
    queries = expand_queries(question, n=n)
    print("=== 生成的检索问句 ===")
    for i, q in enumerate(queries, 1):
        print(f"  [{i}] {q}")
    print()

    best: dict[str, float] = {}
    for q in queries:
        for doc, score in store.similarity_search_with_score(q, k=TOP_K_PER_QUERY):
            key = doc.page_content
            if key not in best or score < best[key]:
                best[key] = score

    ranked = sorted(best.items(), key=lambda x: x[1])
    return ranked


def main() -> None:
    store = build_vectorstore()
    question = "切文档时怎么让前后两段有一点重复，避免句子被切断？"

    print(f"模型: {settings.ollama_model}")
    print(f"原始问句: {question}\n")

    # 对照：只用原问句
    raw_doc, raw_score = store.similarity_search_with_score(question, k=1)[0]
    print("=== 对照 · 原问句直接检索 Top-1 ===")
    print(f"  score={raw_score:.4f}")
    print(f"  预览: {raw_doc.page_content.replace(chr(10), ' ')[:90]}...\n")

    # Multi-Query
    ranked = multi_query_retrieve(store, question, n=3)
    print("=== Multi-Query 合并去重后（按 score 升序）===")
    for i, (content, score) in enumerate(ranked, 1):
        preview = content.replace("\n", " ")[:90]
        hit = "chunk_overlap" in content.lower() or "重叠" in content
        print(f"  [{i}] score={score:.4f}  分块参数段={'是' if hit else '否'}")
        print(f"      {preview}...\n")

    print(
        """【本课要点】
1. Multi-Query：1 问句 → LLM 生成多条检索 query → 分别 similarity_search。
2. 合并时按 chunk 正文去重，同一段只保留最好的 score。
3. 原问句通常也保留，防止改写跑偏丢意图。
下节课：HyDE — 先写「假设答案段落」，再用它去检索。
"""
    )


if __name__ == "__main__":
    main()
