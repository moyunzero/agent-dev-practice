"""第 1 课：关键词检索 vs 语义检索 — 同一知识库，不同问法，两路强弱不同。"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day09_demo"


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
    """极简分词：英文按非字母数字切；中文按字。教学用，不是生产分词器。"""
    import re

    text = text.lower()
    en = re.findall(r"[a-z0-9_]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    return en + zh


def bm25_top1(chunks, query: str):
    corpus = [tokenize(c.page_content) for c in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(tokenize(query))
    best_i = int(max(range(len(scores)), key=lambda i: scores[i]))
    return chunks[best_i], float(scores[best_i])


def vector_top1(store: Chroma, query: str):
    doc, score = store.similarity_search_with_score(query, k=1)[0]
    return doc, float(score)


def preview(text: str, n: int = 70) -> str:
    return text.replace("\n", " ")[:n]


def show(label: str, query: str, chunks, store: Chroma) -> None:
    b_doc, b_score = bm25_top1(chunks, query)
    v_doc, v_score = vector_top1(store, query)
    print(f"【{label}】")
    print(f"  问句: {query}")
    print(f"  BM25  Top-1 score={b_score:.4f} | {preview(b_doc.page_content)}...")
    print(f"  向量  Top-1 dist ={v_score:.4f} | {preview(v_doc.page_content)}...")
    print(f"  两路是否同一段: {'是' if b_doc.page_content == v_doc.page_content else '否'}\n")


def main() -> None:
    chunks = load_chunks()
    store = build_vectorstore(chunks)
    print(f"知识库共 {len(chunks)} 条 chunk\n")

    # 精确错误码：BM25 通常更「咬」住 ERR_CHUNK_42
    show("问法 A · 精确错误码（关键词友好）", "ERR_CHUNK_42 怎么处理？", chunks, store)

    # 口语同义、几乎不出现文档原词：向量通常更稳
    show(
        "问法 B · 口语同义（语义友好）",
        "切文档时怎么让前后两段有一点重复，避免句子被切断？",
        chunks,
        store,
    )

    print(
        """【本课要点】
1. BM25 = 关键词匹配；向量 = 语义相近。各有盲区。
2. 精确代号 / 专有名词 → 常更吃 BM25；口语同义 → 常更吃向量。
3. Hybrid = 两路都跑，再融合 — 下一课先单独跑通 BM25。
"""
    )


if __name__ == "__main__":
    main()
