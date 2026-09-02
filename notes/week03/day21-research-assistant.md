# 做一周收官的研究助手：把 RAG 和 Web 搜索都挂进同一个 Agent

Week3 分别练过 ReAct、自定义工具、SQL、Function Calling、记忆、重试降级。收官要落到一件事上：  
上游 Day21 目标：**构建一个集成 RAG 和 Web 搜索工具的「研究助手」Agent**。

本文用一份**公网搜不到**的虚构内部笔记（Nebula Router / N7-2026）做本地知识库，再加 DuckDuckGo 网页搜索；两者都变成 `@tool`，交给 `create_agent`。问内部约定应走 RAG；问公开概念应走 Web——轨迹里能看见它选了哪个。

## 你将会得到什么

1. 说清研究助手为什么需要 **两种** 信息源  
2. 把「本地检索」和「网页搜索」封装成工具并单独测通  
3. 用 Ollama + `create_agent` 跑通双工具选型  
4. 用改笔记 → 重建索引 → 再问，验证答案跟着知识库变  

---

## 零基础名词表

> 建议先读完再动手。

### 研究助手（Research Assistant）

| 层 | 说明 |
|----|------|
| **是什么** | 能按问题去查资料、再组织答案的 Agent，而不是只靠模型「背过的参数」 |
| **在本文干什么** | 同时挂本地 RAG + 网页搜索，完成 Week3 综合小项目 |
| **怎么区分** | 不是第二个聊天机器人皮肤；关键是**有没有检索/搜索工具**以及**会不会选对** |

### RAG 工具（本地知识库检索）

| 层 | 说明 |
|----|------|
| **是什么** | 把「在私有文档上做向量检索」封装成 Agent 可调用的函数 |
| **在本文干什么** | `search_knowledge_base` → Chroma 查 `nebula_notes.md` |
| **怎么区分** | RAG 回答**你库里有的**；库外新闻不该硬用 RAG 瞎答 |

```text
笔记.md → 分块 → Embedding → Chroma
                ↑
用户问内部细节 → Agent 调 search_knowledge_base → 返回相关片段
```

### Web 搜索工具

| 层 | 说明 |
|----|------|
| **是什么** | 把「搜公开网页」封装成工具；本文用 DuckDuckGo（`ddgs`），免 Key |
| **在本文干什么** | `web_search` → 返回若干标题/摘要/链接 |
| **怎么区分** | 公网**没有**你的内部协议；用 Web 查 N7-2026 会对不上笔记 |

### 为什么要用虚构的 Nebula 笔记

| 层 | 说明 |
|----|------|
| **是什么** | 故意写一套公网不存在的约定：协议 **N7-2026**、桶数 **64**、超时 **900ms** 等 |
| **在本文干什么** | 验收：只有走知识库才能答对；模型瞎编或误走 Web 容易露馅 |
| **怎么区分** | 教学用假项目 ≠ 生产保密方案；生产要用真权限与审计 |

### ReAct 轨迹（复习）

| 层 | 说明 |
|----|------|
| **是什么** | Thought / Action / Observation / Answer 的循环（见 Week3 Day15） |
| **在本文干什么** | 打印工具名与参数，确认选了 `search_knowledge_base` 还是 `web_search` |
| **怎么区分** | Thought/Action ≈ 模型点单；Observation ≈ 工具回传；Answer ≈ 最终对人说的话 |

### 工具返回字符串 vs 抛异常

| 方式 | 影响 |
|------|------|
| **返回说明字符串**（如「网页搜索失败：…」） | 结果进对话，模型可据此改口或提示用户 |
| **未捕获异常** | 整轮 Agent 可能中断（与 Day20 韧性同一道理） |

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) + 支持 tools 的模型（如 `qwen2:7b`）  
- 首次建索引会下载 `sentence-transformers/all-MiniLM-L6-v2`  
- 网页搜索需要外网；失败时工具返回可读错误，不强制成功  

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day21-research-assistant && cd day21-research-assistant
mkdir -p data
```

### `pyproject.toml`

```toml
[project]
name = "day21-research-assistant"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "chromadb>=0.5.0",
  "ddgs>=9.0.0",
  "langchain>=1.0",
  "langchain-chroma>=0.2.0",
  "langchain-community>=0.3.0",
  "langchain-huggingface>=0.1.0",
  "langchain-ollama>=0.3",
  "langchain-text-splitters>=0.3.0",
  "langgraph>=0.2",
  "sentence-transformers>=3.0.0",
]
```

```bash
uv sync
```

### `data/nebula_notes.md`（节选）

```markdown
# Project Nebula — 内部研究笔记

- 内部协议版本：**N7-2026**
- 路由表双层哈希，桶数固定为 **64**
- 超时默认 **900ms**
```

完整笔记可含负责人、降级策略、已知问题等；关键是：**这些字符串公网搜不到**。

### `rag_store.py`

```python
from pathlib import Path
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "nebula_notes.md"
PERSIST = ROOT / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "day21_nebula"


def get_vectorstore(*, rebuild: bool = False) -> Chroma:
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if rebuild and PERSIST.exists():
        import shutil
        shutil.rmtree(PERSIST)
    if PERSIST.exists() and not rebuild:
        return Chroma(
            persist_directory=str(PERSIST),
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=280, chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    ).split_documents(docs)
    return Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name=COLLECTION,
    )


def search_kb(query: str, *, k: int = 2) -> str:
    hits = get_vectorstore().similarity_search(query, k=k)
    if not hits:
        return "知识库无命中。"
    return "\n\n".join(f"[{i}] {d.page_content.strip()}" for i, d in enumerate(hits, 1))
```

### `research_tools.py`

```python
from langchain.tools import tool
from rag_store import search_kb


@tool
def search_knowledge_base(query: str) -> str:
    """检索本地内部知识库（Nebula / N7-2026）。问协议、桶数、超时时用本工具。"""
    return search_kb(query)


@tool
def web_search(query: str) -> str:
    """搜索公开网页。问新闻、通用概念时用；不要用它查 Nebula 内部协议。"""
    try:
        from ddgs import DDGS
        rows = list(DDGS().text(query, max_results=3))
    except Exception as e:
        return f"网页搜索失败：{e}"
    if not rows:
        return "网页搜索无结果。"
    parts = []
    for i, r in enumerate(rows, 1):
        parts.append(
            f"[{i}] {r.get('title','')}\n{r.get('body') or ''}\n来源: {r.get('href','')}"
        )
    return "\n\n".join(parts)
```

### 先不经 Agent 测工具

```python
from rag_store import get_vectorstore, search_kb
from research_tools import web_search

get_vectorstore(rebuild=True)
print(search_kb("Nebula Router 协议版本和桶数"))
print(web_search.invoke({"query": "What is DuckDuckGo"}))
```

期望：本地命中含 **N7-2026** / **64**；网页侧有 DuckDuckGo 相关摘要。

### `demo_research_agent.py`（核心）

```python
import os, sys
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from rag_store import get_vectorstore
from research_tools import search_knowledge_base, web_search

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")
get_vectorstore()

question = sys.argv[1] if len(sys.argv) > 1 else (
    "Nebula Router 的内部协议版本和桶数分别是什么？请依据知识库回答。"
)

agent = create_agent(
    model=f"ollama:{OLLAMA_MODEL}",
    tools=[search_knowledge_base, web_search],
    system_prompt=(
        "你是研究助手。内部/私有细节必须调用 search_knowledge_base；"
        "公开概念调用 web_search。禁止编造 N7 / Nebula 细节。"
    ),
)
result = agent.invoke({"messages": [{"role": "user", "content": question}]})
# 打印 tool_calls / ToolMessage / 最终 AIMessage …
```

```bash
uv run python demo_research_agent.py
```

期望轨迹：`search_knowledge_base`；Answer 含 **N7-2026** 与 **64**。

公网对照：

```bash
uv run python demo_research_agent.py "用网页搜索简要说明什么是 DuckDuckGo"
```

改笔记后记得重建索引，否则仍读旧向量：

```bash
uv run python -c "from rag_store import get_vectorstore; get_vectorstore(rebuild=True)"
```

---

## 新手向坑

| 现象 | 原因 | 处理 |
|------|------|------|
| 改了 md，答案仍是旧数字 | Chroma 未重建 | `get_vectorstore(rebuild=True)` |
| 内部题却调了 `web_search` | 模型选型偶发漂移 | 强化 system / 工具 docstring；问题写明「依据知识库」 |
| `web_search` 失败 | 无外网或被拦 | 读工具返回的失败字符串即可；离线仍可用 RAG 题验收 |
| 首次极慢 | 下载 embedding / torch | 属首次成本；之后会快很多 |

---

## 边界：做了什么 / 故意没做什么

**做了**

- 本地 RAG 工具 + DuckDuckGo Web 工具  
- `create_agent` 双工具研究助手  
- 用私有虚构笔记验收「真的走了知识库」  

**故意没做**

- Week2 的 Hybrid / Rerank / Milvus 全套（今日只要求「挂成工具」）  
- 付费搜索 API、权限与审计  
- 多 Agent 分工编排  

---

## 一句话收束

**研究助手 = 本地 RAG（私有真相）+ Web 搜索（公网补充）；Agent 负责选型，工具负责取证，答案才站得住。**
