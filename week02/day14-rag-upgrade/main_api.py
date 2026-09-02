"""Day14 补洞：把升级 RAG 挂成 FastAPI（对齐 Week1「系统」形态）。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from upgraded_pipeline import ask

app = FastAPI(title="Day14 Upgraded RAG API", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, examples=["ERR_CHUNK_42 怎么处理？"])
    generate: bool = Field(default=True, description="是否调用 Ollama 生成；False 只返回检索 sources")


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    pipeline: str
    sources: list[dict]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "day14-upgraded-rag"}


@app.post("/ask", response_model=AskResponse)
def post_ask(body: AskRequest) -> AskResponse:
    try:
        result = ask(body.question, generate=body.generate)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=str(e)) from e
    return AskResponse(**result)
