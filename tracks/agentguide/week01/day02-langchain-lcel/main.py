"""Day 2: LangChain LCEL chain + FastAPI（Ollama / OpenRouter）。"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:0.6b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"


settings = Settings()
app = FastAPI(title="Day02 LangChain LCEL", version="0.1.0")


class ChainRequest(BaseModel):
    question: str = Field(min_length=1, examples=["FastAPI 是什么？"])
    provider: Literal["ollama", "openrouter"] = "ollama"
    temperature: float = Field(default=0.2, ge=0, le=2)


class ChainResponse(BaseModel):
    provider: str
    model: str
    answer: str


def _llm(provider: Literal["ollama", "openrouter"], temperature: float) -> tuple[ChatOpenAI, str]:
    if provider == "ollama":
        return (
            ChatOpenAI(
                base_url=settings.ollama_base_url,
                api_key="ollama",
                model=settings.ollama_model,
                temperature=temperature,
            ),
            settings.ollama_model,
        )

    if not settings.openrouter_api_key:
        raise HTTPException(status_code=400, detail="缺少 OPENROUTER_API_KEY，请写入 .env")

    return (
        ChatOpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            temperature=temperature,
        ),
        settings.openrouter_model,
    )


def build_chain(provider: Literal["ollama", "openrouter"], temperature: float = 0.2):
    """LCEL：Prompt | Model | OutputParser —— 用 | 把三步串成一条链。"""
    llm, model_name = _llm(provider, temperature)
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "你是简洁助手。只用一句话回答，不要废话。"),
            ("human", "{question}"),
        ]
    )
    chain = prompt | llm | StrOutputParser()
    return chain, model_name


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chain", response_model=ChainResponse)
def run_chain(body: ChainRequest) -> ChainResponse:
    chain, model_name = build_chain(body.provider, body.temperature)
    try:
        answer = chain.invoke({"question": body.question})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"LCEL 调用失败: {exc}") from exc
    return ChainResponse(provider=body.provider, model=model_name, answer=answer)
