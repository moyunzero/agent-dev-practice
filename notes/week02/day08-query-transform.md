# 检索前先改写问句：手撕 Multi-Query 与 HyDE

Naive RAG 的常见做法是：用户说什么，就用**原问句**去向量库搜。问题在于——用户说话像口语，文档写得像术语，两边对不上时，检索会偏，后面 Prompt 再严谨也救不回来。

**Query Transformation（查询改写）** 解决的就是这件事：在检索**之前**，把问句变成更适合搜索的形式。本文从零讲清概念，并实现两种最常用策略：**Multi-Query** 与 **HyDE**，最后接到一条可跑的 RAG 链。全文自包含，按步骤复制即可复现。

## 你将会得到什么

1. 说清 Query Transformation 是什么、插在 RAG 哪一步  
2. 跑通 Multi-Query：1 问句 → 多路检索 → 合并去重  
3. 跑通 HyDE：先写「假设资料」→ 用假资料去检索  
4. 理解 HyDE 可能跑偏，以及如何用原问句检索兜底  
5. 用 `--mode none|multi_query|hyde` 对比三种检索前策略  

---

## 零基础名词表

### RAG 在干什么（30 秒）

**RAG**（Retrieval-Augmented Generation）= 让大模型先查资料、再回答：

```text
用户问句 → 向量检索（找相关段落）→ 塞进 Prompt → 大模型生成答案
```

向量库里存的是文档切成的 **chunk**（小段文字）。检索质量差，答案上限就低。

### Query Transformation 是什么？

**Query Transformation** = 查询改写 / 查询变换。

在**检索之前**，用规则或大模型，把用户的原始问句变成**更适合去搜**的形式。

它**不**改文档、**不**改向量库、**不**直接给出最终答案——只改「拿什么去问索引」。

类比：进图书馆找书时，先把口语问题改成更贴近目录分类的关键词，再去检索。

### 插在链路哪一步？

```text
用户问句
  ↓
【Query Transformation】  ← 本文重点
  ↓
向量检索 Top-K
  ↓
拼 Prompt + 大模型生成
```

### 两种策略一览

| 策略 | 做什么 | 适合什么场景 |
|------|--------|--------------|
| **Multi-Query** | 1 个问句 → 生成多条不同说法 → 分别搜再合并 | 一种问法容易漏、召回不足 |
| **HyDE** | 先写一段「假想资料」→ 用假资料的向量去搜真文档 | 问句与文档表述差距大 |

> Multi-Query 扩展的是**问法**；HyDE 扩展的是**文档形态（假设段落）**。

---

## 环境准备

**需要**：Python 3.12+、[uv](https://docs.astral.sh/uv/)、[Ollama](https://ollama.com/) 本地运行

```bash
mkdir query-transform-demo && cd query-transform-demo
uv init
uv add chromadb langchain langchain-chroma langchain-community \
       langchain-huggingface langchain-openai langchain-text-splitters \
       pydantic-settings sentence-transformers
mkdir -p data
```

`.env`：

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2:7b
```

确认 Ollama：

```bash
ollama list
curl -s http://localhost:11434/v1/models | head
```

---

## 准备知识库 `data/sample.md`

```markdown
# FastAPI 入门笔记

FastAPI 是一个用于构建 API 的 Python Web 框架。它基于类型注解，能自动生成 OpenAPI 文档。

## 路由

使用 `@app.get` 和 `@app.post` 把 URL 绑定到 Python 函数。

## 请求校验

Pydantic 模型可以描述请求体的形状。非法字段会在进入业务逻辑之前被拒绝，通常返回 HTTP 422。

## 分块参数

- **chunk_size**：每块的最大字符数。太小则上下文碎片化；太大则可能超过模型窗口。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 小结

加载与分割本身不调用大模型，但决定了后面检索质量的上限。
```

---

## 第 1 步：感受「问句—文档鸿沟」

同一意图、不同问法，检索距离可能差很多。保存 `step01_retrieval_gap.py`：

```python
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "qt_demo"


def build_vectorstore() -> Chroma:
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


def show_top1(store: Chroma, label: str, query: str) -> None:
    doc, score = store.similarity_search_with_score(query, k=1)[0]
    preview = doc.page_content.replace("\n", " ")[:90]
    hit = "chunk_overlap" in doc.page_content.lower() or "重叠" in doc.page_content
    print(f"【{label}】")
    print(f"  问句: {query}")
    print(f"  Top-1 score={score:.4f}  命中分块参数段={'是' if hit else '否'}")
    print(f"  预览: {preview}...\n")


def main() -> None:
    store = build_vectorstore()
    print(f"索引就绪，共 {store._collection.count()} 条 chunk\n")
    show_top1(store, "问法 A · 术语", "chunk_overlap 是干什么的？")
    show_top1(store, "问法 B · 口语", "切文档时怎么让前后两段有一点重复，避免句子被切断？")


if __name__ == "__main__":
    main()
```

```bash
uv run python step01_retrieval_gap.py
```

**怎么读输出**：Chroma 默认 score 是距离，**越小越相似**。术语问法通常比口语更近。样例库很小，两边都可能「碰巧命中」；文档一多，口语问法更容易偏。

---

## 第 2 步：Multi-Query（多路查询）

### 思路

```text
用户问句
  → LLM 生成 3～5 条不同检索问句（并保留原问句兜底）
  → 每条各自 similarity_search
  → 按 chunk 正文去重，同一段只保留最好的 score
```

保存 `demo_multi_query.py`：

```python
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
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是检索助手。根据用户问题，生成 {n} 条不同表述的检索问句。\n"
                "要求：每条单独一行；不要编号；覆盖同义说法与术语；只输出问句。",
            ),
            ("human", "{question}"),
        ]
    )
    text = (prompt | make_llm() | StrOutputParser()).invoke({"question": question, "n": n})
    lines = [ln.strip().lstrip("0123456789.-、) ").strip() for ln in text.splitlines()]
    queries = [ln for ln in lines if ln]
    if question not in queries:
        queries.insert(0, question)
    return queries[: n + 1]


def multi_query_retrieve(store: Chroma, question: str, n: int = 3) -> list[tuple[str, float]]:
    queries = expand_queries(question, n=n)
    print("=== 生成的检索问句 ===")
    for i, q in enumerate(queries, 1):
        print(f"  [{i}] {q}")

    best: dict[str, float] = {}
    for q in queries:
        for doc, score in store.similarity_search_with_score(q, k=TOP_K_PER_QUERY):
            key = doc.page_content
            if key not in best or score < best[key]:
                best[key] = score
    return sorted(best.items(), key=lambda x: x[1])


def main() -> None:
    store = build_vectorstore()
    question = "切文档时怎么让前后两段有一点重复，避免句子被切断？"
    print(f"原始问句: {question}\n")

    raw_doc, raw_score = store.similarity_search_with_score(question, k=1)[0]
    print(f"原问句 Top-1 score={raw_score:.4f}")
    print(f"预览: {raw_doc.page_content.replace(chr(10), ' ')[:90]}...\n")

    ranked = multi_query_retrieve(store, question, n=3)
    print("=== 合并去重后 ===")
    for i, (content, score) in enumerate(ranked, 1):
        print(f"[{i}] score={score:.4f} | {content.replace(chr(10), ' ')[:80]}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_multi_query.py
```

**要点**：`n` 变大（如 3→5）通常问句更多、召回更宽，但噪声也可能变多；去重是必须的，否则同一段会反复塞进 Prompt。

---

## 第 3 步：HyDE（假设文档嵌入）

### 思路

向量库里存的是**文档段落**，不是问句。HyDE 的做法是：让模型先写一段「假想资料」，再用这段去搜真文档。

```text
问句 → LLM 写假资料 → 用假资料 embed 检索 → 得到真 chunk
```

保存 `demo_hyde.py`：

```python
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
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是技术文档作者。根据用户问题，写一段 80～150 字的「假设资料段落」。\n"
                "写成笔记口吻；尽量包含领域术语；只输出段落正文。",
            ),
            ("human", "{question}"),
        ]
    )
    return (prompt | make_llm() | StrOutputParser()).invoke({"question": question})


def hyde_retrieve(store: Chroma, question: str):
    hypo = make_hypothetical_document(question)
    hits = store.similarity_search_with_score(hypo, k=TOP_K)
    return hypo, [(doc.page_content, score) for doc, score in hits]


def main() -> None:
    store = build_vectorstore()
    question = "切文档时怎么让前后两段有一点重复，避免句子被切断？"

    raw_doc, raw_score = store.similarity_search_with_score(question, k=1)[0]
    print(f"原问句 Top-1 score={raw_score:.4f}\n")

    hypo, ranked = hyde_retrieve(store, question)
    print("=== 假设资料段落 ===")
    print(hypo, "\n")
    print("=== 用假设段落检索 ===")
    for i, (content, score) in enumerate(ranked, 1):
        print(f"[{i}] score={score:.4f} | {content.replace(chr(10), ' ')[:80]}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_hyde.py
```

**关键边界**：假设段落**不能**直接当最终答案。它只是检索探针；真正回答必须基于向量库里的真 chunk。

---

## 第 4 步：接到 RAG 链（三种模式对比）

保存 `demo_rag_with_transform.py`：

```python
import argparse

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


def make_llm():
    return ChatOpenAI(
        base_url=settings.ollama_base_url,
        api_key="ollama",
        model=settings.ollama_model,
        temperature=0,
    )


def retrieve_context(store, question: str, mode: str) -> tuple[str, str]:
    if mode == "none":
        docs = store.similarity_search(question, k=TOP_K)
        return "\n\n---\n\n".join(d.page_content for d in docs), "mode=none"

    if mode == "multi_query":
        ranked = multi_query_retrieve(store, question, n=3)[:TOP_K]
        return "\n\n---\n\n".join(c for c, _ in ranked), "mode=multi_query"

    if mode == "hyde":
        hypo, ranked = hyde_retrieve(store, question)
        merged = {c: s for c, s in ranked}
        for doc, score in store.similarity_search_with_score(question, k=1):
            key = doc.page_content
            if key not in merged or score < merged[key]:
                merged[key] = score
        top = sorted(merged.items(), key=lambda x: x[1])[:TOP_K]
        ctx = "\n\n---\n\n".join(c for c, _ in top)
        return ctx, f"mode=hyde + raw fallback\n假设段落预览:\n{hypo[:200]}..."

    raise ValueError(mode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["none", "multi_query", "hyde"], default="multi_query")
    parser.add_argument(
        "--question",
        default="切文档时怎么让前后两段有一点重复，避免句子被切断？",
    )
    args = parser.parse_args()

    store = build_vectorstore()
    context, debug = retrieve_context(store, args.question, args.mode)
    print(debug)
    print("\n=== 资料 ===\n", context[:400], "\n")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "你是文档问答助手。只根据【资料】回答；资料未提及请说「资料未提及」。回答简洁。",
            ),
            ("human", "【资料】\n{context}\n\n【问题】\n{question}"),
        ]
    )
    answer = (prompt | make_llm() | StrOutputParser()).invoke(
        {"context": context, "question": args.question}
    )
    print("=== 回答 ===\n", answer)


if __name__ == "__main__":
    main()
```

对比三种模式：

```bash
uv run python demo_rag_with_transform.py --mode none
uv run python demo_rag_with_transform.py --mode multi_query
uv run python demo_rag_with_transform.py --mode hyde
```

期望：回答应基于资料中的 `chunk_overlap` / 重叠语义；若资料没有相关内容，应输出「资料未提及」，而不是用模型训练知识自由发挥。

---

## 踩过的坑

**1）HyDE 假设段落写偏了**

现象：假资料在讲「过渡词 / 写作连贯」，而不是 `chunk_overlap`；检索 score 甚至比原问句更差。  
原因：LLM 误解了问题领域。  
处理：不要把假资料当答案；生产里常把 **HyDE 检索 ∪ 原问句检索** 合并兜底。

**2）Multi-Query 不去重**

同一 chunk 会被多路问句反复捞到，Prompt 又长又重复，浪费上下文窗口。按正文去重，保留最好 score。

**3）把 Query Transformation 当成「改最终答案」**

它只改检索输入。最终答案仍必须来自真 chunk + 受约束的 Prompt。

**4）样例库太小，对比不明显**

只有 2～3 个 chunk 时，口语问法也可能「碰巧命中」。看 **score**，或换更大文档集，差距会更明显。

**5）Ollama 未启动**

Multi-Query / HyDE 都要调 LLM。先 `ollama list` / `curl localhost:11434`。

---

## 取舍与未做之事

本篇覆盖上游 Day8 目标：**实现 HyDE、Multi-Query 等查询改写策略**。

未涉及：BM25 混合检索、Rerank、Milvus、RAGAs 评估（后续 Advanced RAG 主题）。也未把改写挂到 HTTP API；CLI 对比三种 mode 足够把原理跑通。

---

## 小结

1. **Query Transformation** = 检索前改写；解决问句与文档表述不一致。  
2. **Multi-Query** = 多问法检索 + 去重合并；原问句常作兜底。  
3. **HyDE** = 用假设资料去搜真文档；假资料不是最终答案，跑偏时用原问句检索补救。  
4. 最终回答仍只信真 chunk；资料没有就说「资料未提及」。  

下一步常见方向：混合检索（BM25 + 向量）与 Rerank，进一步抬高检索精度。

---

*系列笔记 · Agent 工程跟练 · Week 2 Day 8*
