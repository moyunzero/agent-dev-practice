# 手撕 Naive RAG：用 FastAPI + LangChain 做端到端文档问答 API

Day3 你把文档切成了 chunk，Day4 你把 chunk 存进了 Chroma 并能 Top-K 检索。但用户不会直接跑 Python 脚本——他们要通过 **HTTP 问一个问题，拿到一个答案**。

这就是 **Naive RAG** 的完整闭环：检索 → 拼 Prompt → 模型生成 → API 返回。本文把 Day1（FastAPI）、Day2（LCEL）、Day3/4（加载/向量检索）串成 **`POST /ask`**。全文自包含，代码可直接复制运行。

## 你将会得到什么

1. 说清 Naive RAG 四步：检索 → 拼 Prompt → LCEL 生成 → FastAPI 暴露  
2. 跑通 CLI 版 RAG 链（`demo_rag_chain.py`）  
3. 跑通 HTTP 版：`POST /ask` 返回 `answer` + `sources`  
4. 理解 `sources`、Prompt 约束、Ollama 失败时 502 的含义  

---

## 零基础名词表

### Naive RAG 是什么

**Naive RAG** = 最直白的检索增强生成：

```text
问句 → 检索相关 chunk → 塞进 Prompt → 模型根据资料回答
```

没有 Rerank、Query 改写、Agent 等「高级技巧」—— 先把这条主线跑通。

### 本篇在 Week1 的位置

```text
Day1  FastAPI          HTTP 入口
Day2  LCEL             prompt | model | parser
Day3  Loader/Splitter   文档 → chunk
Day4  Embedding/Chroma chunk → 向量索引 → Top-K
Day5-6（本篇）         上面全部串起来 → POST /ask
```

---

## 环境准备

**需要**：Python 3.12+、[uv](https://docs.astral.sh/uv/)、[Ollama](https://ollama.com/) 本地运行

```bash
uv init naive-rag-day5 && cd naive-rag-day5
uv add fastapi uvicorn chromadb langchain langchain-chroma langchain-community \
       langchain-huggingface langchain-openai langchain-text-splitters \
       pydantic-settings sentence-transformers
mkdir -p data
```

`.env`（复制后按本机模型修改）：

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2:7b
```

确认 Ollama 可用：

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

- **chunk_size**：每块的最大字符数。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 小结

加载与分割本身不调用大模型，但决定了后面检索质量的上限。
```

---

## 第 1 步：检索结果如何进 Prompt（先不调 LLM）

保存 `step01_retrieve_and_prompt.py`：

```python
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path("data/sample.md")
PERSIST = Path("chroma_db")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
TOP_K = 2


def build_vectorstore() -> Chroma:
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40).split_documents(docs)
    if PERSIST.exists():
        shutil.rmtree(PERSIST)
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    return Chroma.from_documents(chunks, embeddings, persist_directory=str(PERSIST), collection_name="naive_rag")


def main() -> None:
    store = build_vectorstore()
    question = "chunk_overlap 是干什么的？"
    docs = store.similarity_search(question, k=TOP_K)
    context = "\n\n---\n\n".join(d.page_content for d in docs)
    prompt = f"""请仅根据以下资料回答问题。资料中没有的信息请说「资料未提及」。

【资料】
{context}

【问题】
{question}
"""
    print(prompt)


if __name__ == "__main__":
    main()
```

```bash
uv run python step01_retrieve_and_prompt.py
```

**要点**：Day4 结束在 Top-K chunk；Day5 新的一步是把 chunk **正文**（`page_content`）拼进 Prompt。向量只负责「找」，进 Prompt 的是**文字**。

---

## 第 2 步：LCEL RAG 链（CLI）

保存 `demo_rag_chain.py`：

```python
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA = Path("data/sample.md")
PERSIST = Path("chroma_db")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "naive_rag"
TOP_K = 2


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen2:7b"


settings = Settings()


def get_vectorstore() -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if PERSIST.exists():
        return Chroma(persist_directory=str(PERSIST), embedding_function=embeddings, collection_name=COLLECTION)
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40).split_documents(docs)
    return Chroma.from_documents(chunks, embeddings, persist_directory=str(PERSIST), collection_name=COLLECTION)


def build_rag_chain(store: Chroma):
    llm = ChatOpenAI(base_url=settings.ollama_base_url, api_key="ollama", model=settings.ollama_model, temperature=0)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是文档问答助手。只根据【资料】回答；没有的请说「资料未提及」。回答简洁。"),
        ("human", "【资料】\n{context}\n\n【问题】\n{question}"),
    ])

    def retrieve_context(inputs: dict) -> str:
        docs = store.similarity_search(inputs["question"], k=TOP_K)
        return "\n\n---\n\n".join(d.page_content for d in docs)

    return {"context": retrieve_context, "question": lambda x: x["question"]} | prompt | llm | StrOutputParser()


def main() -> None:
    chain = build_rag_chain(get_vectorstore())
    answer = chain.invoke({"question": "chunk_overlap 是干什么的？"})
    print(answer)


if __name__ == "__main__":
    main()
```

```bash
uv run python step01_retrieve_and_prompt.py   # 先建索引
uv run python demo_rag_chain.py
```

链的结构：

```text
{ context, question }  →  retrieve_context 自动检索
        | prompt
        | llm（Ollama）
        | StrOutputParser
      答案字符串
```

---

## 第 3 步：FastAPI `POST /ask`

保存 `main.py`：

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from demo_rag_chain import TOP_K, build_rag_chain, get_vectorstore, settings

app = FastAPI(title="Naive RAG", version="0.1.0")
store = get_vectorstore()
chain = build_rag_chain(store)


class AskRequest(BaseModel):
    question: str = Field(min_length=1)


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
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"RAG 调用失败: {exc}") from exc

    docs = store.similarity_search(body.question, k=TOP_K)
    sources = [
        SourceItem(metadata=d.metadata, preview=d.page_content[:120].replace("\n", " "))
        for d in docs
    ]
    return AskResponse(question=body.question, answer=answer, model=settings.ollama_model, sources=sources)
```

启动与验证：

```bash
uv run uvicorn main:app --reload --port 8002
```

```bash
curl -s http://127.0.0.1:8002/health

curl -s -X POST http://127.0.0.1:8002/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"chunk_overlap 是干什么的？"}'
```

期望 JSON 含：

- `answer`：模型根据资料生成的回答  
- `sources`：检索到的 chunk 预览 + `metadata`（如 `source` 文件路径）  
- `model`：使用的 Ollama 模型名  

也可打开 `http://127.0.0.1:8002/docs` 在 Swagger 里试。

---

## 关系图：一次 `/ask` 里发生了什么

`main.py` 收到问句后做**两件事**，最后打包成一个 JSON：

```text
POST /ask { "question": "..." }
        │
        ├─ ① chain.invoke(question)
        │      └─ 链内：检索 Top-K → 拼 Prompt → 调 Ollama
        │      └─ 产出：answer（给用户的回答）
        │
        └─ ② similarity_search(question, k=TOP_K)
               └─ 产出：sources（chunk 预览 + metadata，给调用方溯源）

        return { question, answer, sources, model }
```

教学版为清晰起见检索了两次（生成答案一次、组装 `sources` 一次）；生产环境可合并成一次检索。

---

## 踩过的坑

**1）Prompt 不写「仅根据资料回答」**

模型会用训练知识自由发挥，出现**幻觉**—— 看起来对，其实不是你文档里的内容。

**2）`sources` 的 metadata 不是「向量从哪来」**

`metadata` 是**文档来源**（如 `{"source": "data/sample.md"}`），`preview` 是 chunk 原文摘要。向量只参与检索，不直接返回给调用方。

**3）Ollama 没启动 → 502，不是 404**

`main.py` 捕获 LLM 调用异常并返回 **502 Bad Gateway**。404 通常是 URL 路径写错。

**4）`Address already in use`**

端口被占用：`lsof -i :8002` 查 PID，`kill <PID>` 或换 `--port 8003`。

**5）`TOP_K` 太小，回答变短或不完整**

`k=1` 只塞 1 段资料进 Prompt，上下文更少，回答往往更短；若 Top-1 检索偏了，答案也会不准。`k=2~3` 是常见起点。

**6）重复入库 / 重复检索**

教学版 `main.py` 为清晰起见，生成答案和组装 `sources` 各检索一次。生产环境可合并成一次检索，把同批 chunk 既给 Prompt 又给 `sources`。

---

## 取舍与未做之事

本篇覆盖上游 Day5–6：**FastAPI + LangChain 端到端文档问答 API**。

未涉及：流式输出、多文档上传、Rerank、Hybrid Search、对话历史（Week2+）。  
索引在启动时从 `sample.md` 构建；生产环境通常离线建索引、在线只检索。

---

## 小结

Naive RAG 四步：

1. **检索** Top-K chunk（Day3/4）  
2. **拼 Prompt** 资料 + 问题（Day5）  
3. **LCEL 生成** `prompt | llm | parser`（Day2）  
4. **FastAPI** `POST /ask` 暴露（Day1）  

下一步 Day7：把本周 RAG 服务 **Docker 打包**，在新环境一条命令跑起来。

---

*系列笔记 · Agent 工程跟练 · Week 1 Day 5–6*
