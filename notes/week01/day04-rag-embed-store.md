# 理解 Embedding 并用 Chroma 构建本地向量索引：RAG 的第二步

Day3 你把文档切成了 **chunk**。但用户提问时，不能对每个 chunk 做 Ctrl+F，也不能把全部 chunk 塞进 Prompt。需要先把文本变成**向量**，存进**向量库**，再按相似度取出 Top-K——这就是 RAG Part 2：**向量化（Embedding）+ 存储（Vector Store）**。

本文从零讲清：Embedding 在算什么、怎么用 `sentence-transformers` 把 chunk 变成向量、怎么用 **Chroma** 建本地索引并做 Top-K 检索。全文自包含，代码可直接复制运行。**本篇到检索为止，不调用 LLM 生成答案**（Day5–6 再接 Prompt + 模型）。

## 你将会得到什么

1. 说清 Embedding、向量库、Top-K 检索各自干什么  
2. 理解余弦相似度 vs L2 距离的直觉  
3. 跑通：chunk → embed → Chroma 入库 → 问句检索  
4. 能解释：入库与检索必须用**同一个** Embedding 模型  
5. 知道检索「不完美」时，和 Day3 分块策略的关系  

---

## 零基础名词表

### RAG 在本篇的位置

```text
Day3 chunk[]
    ↓  Embedding（本篇）     文本 → 固定维度向量
向量 + 原文 + metadata
    ↓  Vector Store（本篇）  Chroma / FAISS 等
可检索索引
    ↓  similarity_search
Top-K 相关 chunk
    ↓  （Day5–6）塞进 Prompt → LLM 生成答案
```

### Embedding 是什么

**Embedding** = 用模型把一段文本映射成一个**数字向量**（例如 384 维浮点数组）。

直觉：**语义相近**的文本 → 向量**方向接近** → 相似度分数高（或距离小）。

### Vector Store 是什么

**向量库**不只存向量，每条记录通常包含：

| 部分 | 作用 |
|------|------|
| **向量** | 算相似度用 |
| **page_content** | chunk 原文，检索后要塞进 Prompt |
| **metadata** | 来源（`source`）、页码（`page`）、章节（`h2`）等，便于溯源 |

### Top-K 是什么

用户问一句 → 问句也 embed 成向量 → 与库中所有 chunk 向量比相似度 → 取**最相关的前 K 条**。

---

## 相似度：余弦 vs L2 距离

| 度量 | 直觉 | 怎么判断「更相似」 |
|------|------|-------------------|
| **余弦相似度** | 两向量夹角 | **越大越相似**（接近 1） |
| **L2 距离**（Chroma 默认 score） | 两向量直线距离 | **越小越相似**（接近 0） |

都在同一维度的向量空间里算，只是**数字含义不同**——不要混用「越大越好」和「越小越好」。

---

## 环境准备（从零开始）

```bash
uv init rag-embed-store-day4 && cd rag-embed-store-day4
uv add chromadb langchain langchain-chroma langchain-community \
       langchain-huggingface langchain-text-splitters sentence-transformers
mkdir -p data
```

确认安装：

```bash
uv run python -c "from langchain_chroma import Chroma; print('ok')"
```

首次运行 Embedding 脚本会下载模型 `all-MiniLM-L6-v2`（约 80MB）。

---

## 准备 `data/sample.md`

与 Day3 相同的学习用 Markdown（节选）：

```markdown
# FastAPI 入门笔记

FastAPI 是一个用于构建 API 的 Python Web 框架。它基于类型注解，能自动生成 OpenAPI 文档。

## 路由

使用 `@app.get` 和 `@app.post` 把 URL 绑定到 Python 函数。函数返回的字典会自动变成 JSON。

## 请求校验

Pydantic 模型可以描述请求体的形状。非法字段会在进入业务逻辑之前被拒绝，通常返回 HTTP 422。

## 分块参数

- **chunk_size**：每块的最大字符数。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 小结

加载与分割本身不调用大模型，但决定了后面检索质量的上限。
```

---

## 第 1 步：余弦相似度直觉（玩具向量）

保存为 `step01_cosine_intuition.py`：

```python
import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def main() -> None:
    cat = [1.0, 0.9, 0.1]
    dog = [0.95, 0.85, 0.15]
    car = [0.1, 0.2, 0.95]
    query = [0.98, 0.88, 0.12]

    print("猫 vs 狗:", f"{cosine_similarity(cat, dog):.3f}")
    print("猫 vs 汽车:", f"{cosine_similarity(cat, car):.3f}")
    for title, vec in [("猫", cat), ("狗", dog), ("汽车", car)]:
        print(f"  问「宠物」vs {title}: {cosine_similarity(query, vec):.3f}")


if __name__ == "__main__":
    main()
```

```bash
uv run python step01_cosine_intuition.py
```

期望：猫/狗相似度远高于汽车——RAG 检索靠**语义**，不是关键字。

---

## 第 2 步：真实 Embedding 模型

保存为 `step02_embed_texts.py`：

```python
from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    model = SentenceTransformer(MODEL)
    texts = [
        "FastAPI 是一个 Python Web 框架，用于构建 API。",
        "FastAPI 基于类型注解，能自动生成 OpenAPI 文档。",
        "今天天气很好，适合出去散步。",
    ]
    labels = ["A", "B", "C"]
    embeddings = model.encode(texts)
    print(f"向量维度: {embeddings.shape[1]}")  # 384

    query = "FastAPI 怎么用来写接口？"
    query_vec = model.encode(query)
    scores = cos_sim(query_vec, embeddings)[0]
    for label, text, score in sorted(zip(labels, texts, scores), key=lambda x: x[2], reverse=True):
        print(f"  {score:.3f}  [{label}] {text}")


if __name__ == "__main__":
    main()
```

要点：**入库和检索必须用同一个模型**，否则向量空间不一致，检索无意义。

---

## 第 3 步：chunk 入库 Chroma

保存为 `demo_index_chunks.py`：

```python
import shutil
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path("data/sample.md")
PERSIST = Path("chroma_db")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)
    print(f"切分: {len(chunks)} 个 chunk")

    if PERSIST.exists():
        shutil.rmtree(PERSIST)

    embeddings = HuggingFaceEmbeddings(model_name=MODEL)
    vectorstore = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=str(PERSIST),
        collection_name="day04_demo",
    )
    print(f"入库: {vectorstore._collection.count()} 条")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_index_chunks.py
```

- 4 个 chunk → **embed 4 次**（每个 chunk 一次）  
- `chroma_db/` 落盘：向量 + 原文 + metadata  
- **重复运行前先清空**（脚本已 `shutil.rmtree`），否则会追加重复数据  

---

## 第 4 步：Top-K 检索

保存为 `demo_search.py`：

```python
from pathlib import Path

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

PERSIST = Path("chroma_db")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    embeddings = HuggingFaceEmbeddings(model_name=MODEL)
    vectorstore = Chroma(
        persist_directory=str(PERSIST),
        embedding_function=embeddings,
        collection_name="day04_demo",
    )

    query = "FastAPI 怎么做请求体验证？"
    k = 2
    print(f"问句: {query}\nTop-{k}:")
    for i, (doc, score) in enumerate(
        vectorstore.similarity_search_with_score(query, k=k), start=1
    ):
        preview = doc.page_content.replace("\n", " ")[:100]
        print(f"[{i}] score={score:.4f} | {preview}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_index_chunks.py   # 先入库
uv run python demo_search.py
```

检索时：**问句 embed 1 次**；库中 chunk **不再 embed**（入库时已算好）。

`score` 是 **L2 距离，越小越相似**。

---

## 第 5 步：全链路串联

保存为 `demo_rag_retrieve.py`：

```python
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path("data/sample.md")
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    chunks = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40).split_documents(docs)
    embeddings = HuggingFaceEmbeddings(model_name=MODEL)
    store = Chroma.from_documents(chunks, embeddings, collection_name="pipeline")

    for q in ["chunk_overlap 是干什么的？", "FastAPI 路由怎么写？"]:
        print(f"\n问句: {q}")
        for doc, score in store.similarity_search_with_score(q, k=2):
            print(f"  score={score:.4f} | {doc.page_content[:80]}...")


if __name__ == "__main__":
    main()
```

一行 pipeline：

```text
sample.md → TextLoader → RecursiveCharacterTextSplitter
         → HuggingFaceEmbeddings → Chroma → similarity_search → Top-K
```

---

## 关系图

```text
  chunk (Day3)
       │
       ▼
  HuggingFaceEmbeddings  ──►  384 维向量
       │
       ▼
  Chroma  { 向量, page_content, metadata }
       │
       ▼  用户问句（同样 embed）
  similarity_search(query, k=K)
       │
       ▼
  Top-K Document 列表  ──►  Day5 塞进 Prompt
```

---

## 踩过的坑

**1）入库跑两次，条数翻倍**

Chroma `from_documents` 默认**追加**。重复运行 `demo_index_chunks.py` 不清理 → 8 条、检索结果重复。解决：重建索引前 `shutil.rmtree("chroma_db")`。

**2）Top-1 不一定是「最该命中」的那段**

问「路由怎么写」，Top-1 可能是「小结」——因为 Day3 用 `RecursiveCharacter` 按长度切，多节合并进一个 chunk，小模型 + 短文本时排序会偏。说明：**检索质量上限由分块策略决定**（Day3 的 MarkdownHeader、Week2 的 Rerank 都是解法）。

**3）余弦相似度 vs Chroma score 别混**

`step02` 里 cos_sim **越大越好**；`demo_search` 里 score **越小越好**——是不同度量，不是 bug。

**4）入库和检索换了不同 Embedding 模型**

向量维度或空间不一致 → 检索几乎随机。生产环境要把**模型名写进配置**，换模型需**全量重建索引**。

---

## 取舍与未做之事

本篇覆盖上游 Day4：**Embedding 原理 + Chroma 本地索引 + Top-K 检索**。

- 向量库也可选 **FAISS**（上游二选一；Chroma 带持久化与 metadata 更省事）  
- Embedding 也可用 **Ollama embedding** 模型；本仓用 `sentence-transformers` 本地跑，不依赖额外拉模型  
- 未涉及：LLM 生成、Hybrid Search、Rerank、Milvus（Week2+）  

---

## 小结

- **Embedding**：chunk / 问句 → 向量；语义相近则向量近  
- **Chroma**：存向量 + 原文 + metadata；`chroma_db/` 可复用  
- **检索**：问句 embed 1 次 → `similarity_search` → Top-K；L2 score **越小越相似**  
- Day4 输出 Top-K chunk；Day5–6 再接 LLM 完成 Naive RAG  

下一步：把 Top-K chunk 塞进 Prompt，用 Day2 的 LCEL 调模型生成答案。

---

*系列笔记 · Agent 工程跟练 · Week 1 Day 4*
