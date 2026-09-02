# 用 Docker 打包 Naive RAG：一条命令跑通文档问答 API

你已经有一个能 `POST /ask` 的 RAG 服务：FastAPI 接收问句，Chroma 检索 chunk，Ollama 生成答案。在笔记本上 `uvicorn` 能跑，但换一台机器就要重新装 Python、依赖、向量索引——环境不一致，部署也麻烦。

**Docker 的作用**：把「代码 + 依赖 + 向量索引」封进**镜像**，在任何装了 Docker 的机器上 `docker run` 就能起服务。本文把 Week1 的 Naive RAG API 打进容器，并连**宿主机**上的 Ollama。全文自包含，按步骤复制即可复现。

## 你将会得到什么

1. 说清 Docker **镜像**与**容器**的区别  
2. 读懂一份可运行的 `Dockerfile`（分层缓存、COPY 顺序）  
3. `docker build` 构建镜像、`docker run` 启动容器并验证 `/health`、`/ask`  
4. 理解容器如何通过 `host.docker.internal` 访问宿主机 Ollama  
5. Week1（Day1–7）能力串成一张图  

---

## 零基础名词表

### 镜像（Image）与容器（Container）

| 概念 | 是什么 | 类比 |
|------|--------|------|
| **镜像** | 只读模板：文件系统 + 依赖 + 代码 + 配置 | 菜谱 / 类（Class） |
| **容器** | 镜像的运行实例，有进程、端口、生命周期 | 按菜谱做出的蛋糕 / 对象（Object） |

同一镜像可以 `docker run` 出多个容器，互不影响。

### 构建上下文（Build Context）

`docker build` **最后一个参数**是目录路径。Docker 只把这个目录里的文件发给构建引擎；`Dockerfile` 里的 `COPY` 只能从这个目录复制。

`-f` 指定 Dockerfile 路径，可以和构建上下文**不在同一目录**：

```bash
docker build -f path/to/Dockerfile path/to/context
```

### 端口映射 `-p 宿主机端口:容器端口`

容器有独立网络。应用在容器内监听 `8002`，外面默认访问不到。`-p 8080:8002` 表示：用本机 `8080` 转发到容器内 `8002`。

---

## 整体架构

```text
┌──────────────── 宿主机（你的 Mac）────────────────┐
│  Ollama :11434  ←── LLM 生成                      │
│       ▲                                           │
│       │ http://host.docker.internal:11434         │
│  ┌────┴─────────────────────────────────────┐     │
│  │  Docker 容器 naive-rag                    │     │
│  │  FastAPI :8002                            │     │
│  │  + Chroma（chroma_db/）                   │     │
│  │  + sentence-transformers（查问句向量）     │     │
│  │  挂载 ~/.cache/huggingface → 复用 embedding │     │
│  └──────────────────────────────────────────┘     │
│       ▲                                             │
│       │ curl http://127.0.0.1:8002/ask              │
└───────┴─────────────────────────────────────────────┘
```

**设计取舍**：

- **打进镜像**：Python 代码、pip/uv 依赖、已建好的 `chroma_db/`  
- **不打进镜像**：Ollama 大模型（体积大、需 GPU、升级频繁）  
- **挂载卷**：`~/.cache/huggingface`，复用本机已下载的 embedding 模型  

---

## 环境准备

**需要**：

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（macOS / Windows）  
- [Ollama](https://ollama.com/) 在宿主机运行，并已拉模型，例如 `qwen2:7b`  
- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)（仅用于**构建镜像前**在本地生成 `chroma_db/` 和 `uv.lock`）  

确认 Docker：

```bash
docker --version
docker ps
```

确认 Ollama：

```bash
ollama list
curl -s http://localhost:11434/v1/models | head
```

---

## 第 1 步：准备 RAG 项目（容器化之前先本地跑通）

新建目录并初始化：

```bash
mkdir naive-rag && cd naive-rag
uv init
uv add fastapi uvicorn chromadb langchain langchain-chroma langchain-community \
       langchain-huggingface langchain-openai langchain-text-splitters \
       pydantic-settings sentence-transformers
mkdir -p data
```

`pyproject.toml` 依赖段应类似：

```toml
[project]
name = "naive-rag"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "chromadb>=0.5.0",
    "langchain>=0.3.0",
    "langchain-chroma>=0.2.0",
    "langchain-community>=0.3.0",
    "langchain-huggingface>=0.1.0",
    "langchain-openai>=0.3.0",
    "langchain-text-splitters>=0.3.0",
    "fastapi>=0.115.0",
    "pydantic-settings>=2.0.0",
    "sentence-transformers>=3.0.0",
    "uvicorn>=0.32.0",
]
```

`data/sample.md`：

```markdown
# FastAPI 入门笔记

FastAPI 是一个用于构建 API 的 Python Web 框架。

## 分块参数

- **chunk_size**：每块的最大字符数。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。
```

`.env`（本地开发用；**不要**打进镜像）：

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen2:7b
```

`demo_rag_chain.py`（RAG 链 + 向量库）：

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

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
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

    return (
        {"context": retrieve_context, "question": lambda x: x["question"]}
        | prompt
        | llm
        | StrOutputParser()
    )
```

`main.py`（FastAPI 入口）：

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
        SourceItem(metadata=doc.metadata, preview=doc.page_content[:120].replace("\n", " "))
        for doc in docs
    ]
    return AskResponse(
        question=body.question,
        answer=answer,
        model=settings.ollama_model,
        sources=sources,
    )
```

**在本地生成向量索引**（会下载 embedding 模型，只需做一次）：

```bash
uv run python -c "from demo_rag_chain import get_vectorstore; get_vectorstore()"
ls chroma_db/
```

确认 API 本地可跑：

```bash
uv run uvicorn main:app --port 8002
# 另开终端
curl -s http://127.0.0.1:8002/health
```

此时目录应类似：

```text
naive-rag/
├── chroma_db/          ← 必须存在，打进镜像
├── data/sample.md
├── demo_rag_chain.py
├── main.py
├── pyproject.toml
├── uv.lock
└── .env                ← 仅本地用
```

---

## 第 2 步：编写 `.dockerignore`

排除不该进镜像的文件，加快构建、避免泄露密钥：

```text
.venv
__pycache__
.env
*.pyc
.git
```

---

## 第 3 步：编写 `Dockerfile`

在项目根目录创建 `Dockerfile`：

```dockerfile
# 海外网络可改回: FROM python:3.12-slim
FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app

# 国内构建可选：PyPI 加速
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# ① 依赖层（改代码时这层可缓存）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# ② 应用层
COPY main.py demo_rag_chain.py ./
COPY data/ data/
COPY chroma_db/ chroma_db/

# 容器内连宿主机 Ollama（macOS / Windows Docker Desktop）
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
    OLLAMA_MODEL=qwen2:7b

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
```

**逐行要点**：

| 指令 | 作用 |
|------|------|
| `FROM` | 基础 Python 环境 |
| `WORKDIR` | 容器内工作目录 |
| `COPY pyproject.toml` + `RUN uv sync` | 先装依赖，利用层缓存 |
| `COPY chroma_db/` | 带上已建索引，启动即可检索 |
| `ENV OLLAMA_BASE_URL=...host.docker.internal...` | 容器访问宿主机 Ollama |
| `EXPOSE 8002` | 文档声明端口（实际映射靠 `docker run -p`） |
| `CMD` | 容器启动时跑 uvicorn；`0.0.0.0` 表示接受外部连接 |

---

## 第 4 步：构建镜像

在 `naive-rag/` 目录（构建上下文 = 当前目录）：

```bash
docker build -t naive-rag .
```

首次构建可能需 **5～15 分钟**（下载 PyTorch 等）。成功后：

```bash
docker images naive-rag
```

应看到 `naive-rag   latest`，体积约 2～4 GB（含科学计算栈）。

---

## 第 5 步：运行容器并验证

```bash
docker run -d --name naive-rag \
  -p 8002:8002 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  naive-rag
```

- `-d`：后台运行  
- `-p 8002:8002`：宿主机 8002 → 容器 8002  
- `-v ...`：挂载本机 HuggingFace 缓存，避免容器内重新下载 embedding 模型  

**首次启动约等 30～60 秒**（加载 embedding 权重），再测：

```bash
curl -s http://127.0.0.1:8002/health
# 期望: {"status":"ok"}

curl -s -X POST http://127.0.0.1:8002/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"chunk_overlap 是干什么的？"}'
```

期望 JSON 含 `answer`、`sources`、`model`。

改宿主机端口示例（容器内仍是 8002）：

```bash
docker run -d --name naive-rag -p 8080:8002 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  naive-rag

curl -s http://127.0.0.1:8080/health
```

停止并删除容器：

```bash
docker stop naive-rag && docker rm naive-rag
```

---

## 踩过的坑

**1）`docker build` 拉 `python:3.12-slim` 失败（connection reset）**

国内访问 Docker Hub 不稳定。处理：Dockerfile 的 `FROM` 改用镜像加速，例如 `docker.m.daocloud.io/library/python:3.12-slim`；或在 Docker Desktop → Settings → Docker Engine 配置 `registry-mirrors`。

**2）容器里 `localhost:11434` 连不上 Ollama**

容器内的 `localhost` 是**容器自己**，不是宿主机。macOS / Windows 上应使用 `http://host.docker.internal:11434/v1`（已在 Dockerfile `ENV` 中设置）。Linux 生产环境常用 `172.17.0.1` 或 `--add-host=host.docker.internal:host-gateway`。

**3）`curl /health` 无输出，但容器在跑**

启动时要加载 embedding 模型，约 30～60 秒后才监听。先 `docker logs naive-rag` 看是否出现 `Uvicorn running on http://0.0.0.0:8002`。

**4）构建时在镜像里下载 HuggingFace 模型失败**

容器构建环境可能访问不了 HuggingFace。本方案：**构建期不下载模型**，`docker run` 时挂载 `~/.cache/huggingface`（需先在宿主机跑过一次 `get_vectorstore()`）。

**5）忘记 COPY `chroma_db/`**

容器每次启动会重新分块、建索引，慢且可能因网络失败。应在本地建好索引后 `COPY chroma_db/` 进镜像。

**6）把 `.env` 打进镜像**

`.env` 含本机配置，应写入 `.dockerignore`。容器用 `ENV` 或 `docker run -e` 注入环境变量。

---

## Week1 回顾：七天串成一条链

```text
Day1  FastAPI           HTTP 路由、Pydantic 校验
Day2  LangChain LCEL    prompt | llm | parser
Day3  Loader/Splitter   文档 → chunk
Day4  Embedding/Chroma  chunk → 向量索引 → Top-K
Day5-6 Naive RAG        检索 + Prompt + 生成 → POST /ask
Day7  Docker（本篇）     镜像打包 → 任意机器 docker run
```

上游 Day7 目标：**将本周的 RAG 项目用 Docker 打包，并成功运行** — 至此 Week1 手撕 Naive RAG 从开发到容器化闭环完成。

---

## 取舍与未做之事

本篇覆盖：**单服务 Dockerfile + docker run + 连宿主机 Ollama**。

未涉及：Docker Compose 多服务编排、多阶段构建瘦身、把 Ollama 也容器化、K8s 部署、生产级健康检查与日志采集（Week2+ 及后续路线）。

---

## 小结

1. **镜像**是模板，**容器**是运行实例。  
2. `Dockerfile` 先 COPY 依赖、再 COPY 代码与 `chroma_db/`，利于缓存。  
3. Ollama 放宿主机；容器用 `host.docker.internal` 访问。  
4. `docker build -t naive-rag .` → `docker run -p 8002:8002 -v ~/.cache/huggingface:...` → `curl /ask` 验收。  

Week2 将进入 Advanced RAG、Milvus 等生产级话题；本周的 Naive RAG + Docker 基座可以直接在上面迭代。

---

*系列笔记 · Agent 工程跟练 · Week 1 Day 7*
