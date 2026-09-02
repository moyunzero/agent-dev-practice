"""知识库 + 两档检索：Naive（仅向量）vs Hybrid+Rerank（Day9）。"""

from __future__ import annotations

import re
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "eval_demo"
OLLAMA_MODEL = "qwen2:7b"
TOP_K = 2
CANDIDATE_K = 5
RRF_K = 60
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是文档问答助手。只根据用户提供的【资料】回答；资料里没有的请说「资料未提及」。回答简洁。",
        ),
        ("human", "【资料】\n{context}\n\n【问题】\n{question}"),
    ]
)


def load_chunks():
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    return RecursiveCharacterTextSplitter(
        chunk_size=220, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)


def build_vectorstore(chunks):
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if PERSIST.exists():
        return Chroma(
            persist_directory=str(PERSIST),
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )


def tokenize(text: str) -> list[str]:
    text = text.lower()
    en = re.findall(r"[a-z0-9_]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    return en + zh


def bm25_ranked(chunks, query: str) -> list[tuple[str, float]]:
    corpus_tokens = [tokenize(c.page_content) for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(
        zip(chunks, scores, strict=True),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(doc.page_content, float(score)) for doc, score in ranked]


def vector_ranked(store: Chroma, query: str, n: int) -> list[tuple[str, float]]:
    hits = store.similarity_search_with_score(query, k=n)
    hits.sort(key=lambda x: x[1])
    return [(doc.page_content, float(score)) for doc, score in hits]


def rrf_fuse(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    fused: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, (content, _raw) in enumerate(ranked, start=1):
            fused[content] = fused.get(content, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)


def rerank(query: str, candidates: list[str], model: CrossEncoder) -> list[str]:
    pairs = [[query, text] for text in candidates]
    scores = model.predict(pairs)
    ranked = sorted(zip(candidates, scores, strict=True), key=lambda x: x[1], reverse=True)
    return [text for text, _ in ranked]


def tag_chunk(text: str) -> str:
    """按 chunk 内最先出现的主题打标签（同一块可能含多节，不能见 ERR 就标错误码）。"""
    err_pos = text.find("ERR_CHUNK_42")
    overlap_pos = text.lower().find("chunk_overlap")
    positions = [(p, "错误码段") for p in [err_pos] if p >= 0]
    positions += [(p, "分块参数段") for p in [overlap_pos] if p >= 0]
    if not positions:
        return "其它"
    return min(positions, key=lambda x: x[0])[1]


def preview(text: str, n: int = 56) -> str:
    return " ".join(text.split())[:n]


def retrieve_naive(store: Chroma, question: str) -> list[str]:
    docs = store.similarity_search(question, k=TOP_K)
    return [d.page_content for d in docs]


def retrieve_hybrid_rerank(chunks, store: Chroma, question: str) -> list[str]:
    bm25 = bm25_ranked(chunks, question)
    vector = vector_ranked(store, question, n=len(chunks))
    fused = rrf_fuse([bm25, vector])[:CANDIDATE_K]
    candidates = [content for content, _ in fused]
    ce = CrossEncoder(RERANK_MODEL)
    return rerank(question, candidates, ce)[:TOP_K]


def generate_answer(question: str, contexts: list[str]) -> str:
    llm = ChatOpenAI(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
        model=OLLAMA_MODEL,
        temperature=0,
    )
    chain = PROMPT | llm | StrOutputParser()
    context = "\n\n---\n\n".join(contexts)
    return chain.invoke({"context": context, "question": question})


def run_pipeline(
    mode: str,
    question: str,
    chunks,
    store: Chroma,
) -> dict:
    if mode == "naive":
        contexts = retrieve_naive(store, question)
    elif mode == "hybrid_rerank":
        contexts = retrieve_hybrid_rerank(chunks, store, question)
    else:
        raise ValueError(f"unknown mode: {mode}")

    answer = generate_answer(question, contexts)
    return {"question": question, "contexts": contexts, "answer": answer}
