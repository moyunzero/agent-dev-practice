"""第 2 课：LCEL RAG 链 — 检索 + Prompt + Ollama 生成（CLI）。"""

import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "naive_rag"
TOP_K = 1


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2:7b"


settings = Settings()


def get_vectorstore() -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if PERSIST.exists():
        return Chroma(
            persist_directory=str(PERSIST),
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )

    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )


def build_rag_chain(store: Chroma):
    llm = ChatOpenAI(
        base_url=settings.ollama_base_url,
        api_key="ollama",
        model=settings.ollama_model,
        temperature=0,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是文档问答助手。只根据用户提供的【资料】回答；资料里没有的请说「资料未提及」。回答简洁。",
            ),
            ("human", "【资料】\n{context}\n\n【问题】\n{question}"),
        ]
    )

    def retrieve_context(inputs: dict) -> str:
        docs = store.similarity_search(inputs["question"], k=TOP_K)
        return "\n\n---\n\n".join(d.page_content for d in docs)

    chain = (
        {"context": retrieve_context, "question": lambda x: x["question"]}
        | prompt
        | llm
        | StrOutputParser()
    )
    return chain


def main() -> None:
    store = get_vectorstore()
    chain = build_rag_chain(store)

    question = "chunk_overlap 是干什么的？"
    print(f"模型: {settings.ollama_model}")
    print(f"问句: {question}\n")

    answer = chain.invoke({"question": question})
    print("=== 模型回答 ===\n")
    print(answer)

    print(
        """

【本课要点】
LCEL 链：{ context, question } | prompt | llm | parser
  - retrieve_context 在链里自动跑（Day4 检索）
  - prompt 拼好资料+问题（第 1 课）
  - llm 生成（Day2）
下节课：把这条链挂到 FastAPI POST /ask
"""
    )


if __name__ == "__main__":
    main()
