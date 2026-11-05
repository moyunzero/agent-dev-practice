"""Day 1: FastAPI Hello World + Ollama / OpenRouter (OpenAI-compatible)."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from openai import OpenAI
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

app = FastAPI(title="Day01 FastAPI Hello", version="0.1.0")


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, examples=["用一句话介绍 FastAPI"])
    provider: Literal["ollama", "openrouter"] = "ollama"
    # 练习 2：请求体多一个可选字段。不传就用 0.2；传了就用你的值（0~2）
    temperature: float = Field(default=0.2, ge=0, le=2)


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello, World"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "day01"}


# 练习 1：新增一个 GET 路由。浏览器/curl 访问 /version 时，FastAPI 会调用这个函数。
@app.get("/version")
def version() -> dict[str, int | str]:
    return {"day": 1, "app": "day01-fastapi-hello"}


# Day1 补全：路径参数 — URL 里的 {item_id} 会自动进函数参数
@app.get("/items/{item_id}")
def read_item(item_id: int) -> dict[str, int | str]:
    return {"item_id": item_id, "name": f"item-{item_id}"}


# Day1 补全：查询参数 — ?q=xxx&limit=5 这种，有默认值的是可选
@app.get("/search")
def search(q: str, limit: int = 5) -> dict[str, str | int]:
    return {"q": q, "limit": limit}


def _client(provider: Literal["ollama", "openrouter"]) -> tuple[OpenAI, str]:
    if provider == "ollama":
        return (
            OpenAI(base_url=settings.ollama_base_url, api_key="ollama"),
            settings.ollama_model,
        )

    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=400,
            detail="缺少 OPENROUTER_API_KEY。复制 .env.example 为 .env 后填入。",
        )
    return (
        OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        ),
        settings.openrouter_model,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    client, model = _client(body.provider)
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": body.prompt}],
            temperature=body.temperature,  # 练习 2：用请求里的值，不再写死 0.2
        )
    except Exception as exc:  # noqa: BLE001 — Day1 先把错误透出，方便排查
        raise HTTPException(status_code=502, detail=f"{body.provider} 调用失败: {exc}") from exc

    content = completion.choices[0].message.content or ""
    return ChatResponse(provider=body.provider, model=model, content=content)
