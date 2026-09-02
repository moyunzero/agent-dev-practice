"""Day 5–6 第 3 课：FastAPI POST /ask — 端到端文档问答 API。"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from demo_rag_chain import TOP_K, build_rag_chain, get_vectorstore, settings

app = FastAPI(title="Day05-06 Naive RAG", version="0.1.0")

store = get_vectorstore()
chain = build_rag_chain(store)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, examples=["chunk_overlap 是干什么的？"])


class SourceItem(BaseModel):
    metadata: dict
    preview: str


class AskResponse(BaseModel):
    question: str
    answer: str
    model: str
    sources: list[SourceItem]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest) -> AskResponse:
    try:
        answer = chain.invoke({"question": body.question})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"RAG 调用失败: {exc}") from exc

    docs = store.similarity_search(body.question, k=TOP_K)
    sources = [
        SourceItem(metadata=doc.metadata, preview=doc.page_content[:120].replace("\n", " "))
        for doc in docs
    ]

    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.ollama_model,
        sources=sources,
    )
