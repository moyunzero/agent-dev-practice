# BM25 + 向量混合检索与 Rerank：把 RAG 召回做宽、排序做准

Week1 的 Naive RAG 通常只用**向量检索**：问句 embed 后和 chunk 比距离。这对口语、同义说法友好，但对 **错误码、专有名词、精确短语** 可能不稳——用户问 `ERR_CHUNK_42 怎么处理？`，Top-1 却落到「分块参数」段，后面 Prompt 再严谨也救不回来。

**Hybrid Search（混合检索）** 同时跑 **BM25（关键词）** 和 **向量（语义）**，用 **RRF** 融合排序；再用 **Rerank（精排）** 在候选里挑出最相关的几条。本文从零讲清概念，手撕 BM25 → Hybrid → CrossEncoder Rerank，并对比四档流水线。全文自包含，按步骤复制即可复现。

## 你将会得到什么

1. 说清 BM25 与向量检索各自擅长什么  
2. 实现 BM25 + Chroma 向量 + RRF 融合  
3. 用本地 CrossEncoder 做 Rerank（与 Cohere Rerank 同角色，免 API Key）  
4. 对比「仅向量 / 仅 BM25 / Hybrid / Hybrid+Rerank」四档差异  
5. 理解召回（宽）与精排（准）的分工  

---

## 零基础名词表

读正文前，先把下面几个词搞懂。不必背公式，能用自己的话讲清「输入是什么、输出是什么、解决什么问题」即可。

### 先复习 30 秒：RAG 检索在干什么？

RAG 不会把整本手册塞进大模型，而是：

```text
用户问句 → 从向量库里找出最相关的几段 chunk → 塞进 Prompt → 大模型根据资料回答
```

**检索质量 = 后面答案质量的上限。** 问句和文档对不上、或者排序错了，Prompt 写得再好也会答偏。

本篇只动**检索这一段**：怎么「捞得更全」（召回）、怎么「排得更准」（精排）。

---

### 向量检索（密集检索 / Dense Retrieval）

**是什么**  
把一段文字变成一个**向量**（一串数字，例如 384 维），表示这段文字的「语义位置」。问句也变成向量，然后在库里找**距离最近**的 chunk。

**怎么工作（直觉版）**

```text
文档 chunk  →  Embedding 模型  →  向量 v_doc
用户问句    →  Embedding 模型  →  向量 v_query
                                    ↓
                            比 v_query 和 v_doc 的距离
                                    ↓
                            距离最小的 Top-K 段
```

问句和文档是**分开**编码的（这叫 **Bi-Encoder**），算距离很快，适合从成千上万段里先粗捞一批。

**擅长什么**

| 场景 | 例子 |
|------|------|
| 口语、不知道专业术语 | 「怎么让前后两段有一点重复？」→ 可能对应 `chunk_overlap` |
| 同义、近义说法 | 「轿车」和「汽车」在向量空间里往往比较近 |
| 描述性意图 | 「多个异步任务一起跑，一个挂了不影响别的」→ 可能对应 `asyncio.gather` |

**不擅长什么**

| 场景 | 为什么 |
|------|--------|
| 精确错误码、ID | `ERR_CHUNK_42` 和「分块参数」在语义上都在讲「文档切块」，向量可能把无关段排到前面 |
| 罕见专有名词 | 训练语料里少见的词，向量表示不稳定 |
| 需要「字面命中」 | 用户就是要搜某个 API 全名，embedding 可能「觉得像」但不是那一段 |

**分数怎么读**  
Chroma 默认使用 **`cosine`（余弦）** 作为相似度度量；`similarity_search_with_score` 返回的是**余弦距离**（可理解为 `1 - cosine_similarity`，归一化向量下常见范围约 [0, 2]），**数值越小表示越相似**。创建 collection 时也可通过 `metadata={"hnsw:space": "cosine"}` / `l2` / `ip` 等改为其它度量，但**默认是 cosine，不是 L2**。不要和 BM25 的「越大越好」搞反。

---

### BM25（稀疏检索 / 关键词检索）

**是什么**  
不走向量，而是看问句里的**词**在不在文档里、出现得是否「有信息量」。BM25 是搜索引擎里用了几十年的经典打分公式之一。

**怎么工作（直觉版）**

```text
问句分词 → ["err", "chunk", "42", "怎么", "处理"]
                ↓
对每个 chunk：这些词在不在？出现几次？chunk 是不是太长被稀释？
                ↓
            得到一个 BM25 分数（越大越相关）
```

**「稀疏」是什么意思**  
大部分词在某篇文档里**不出现**，词表矩阵里大量是 0，所以叫稀疏；向量是稠密的一长串小数。

**擅长什么**

| 场景 | 例子 |
|------|------|
| 错误码、工单号、SKU | `ERR_CHUNK_42 怎么处理？` → 必须命中含 `ERR_CHUNK_42` 的段 |
| API / 函数 / 参数名 | `asyncio.gather` 的 `return_exceptions` |
| 用户几乎原样打出文档里的词 | 复制粘贴报错信息来搜 |

**不擅长什么**

| 场景 | 为什么 |
|------|--------|
| 同义词 | 「轿车」搜不到只写了「汽车」的文档 |
| 口语改写 | 问句里完全没有 `chunk_overlap` 这几个字，BM25 可能打很低分 |
| 跨语言、错别字 | 词对不上就不得分 |

**分数怎么读**  
BM25：**分数越大越相关**。和 Chroma 距离方向相反，这是后面要用 RRF 而不能直接混分数的原因之一。

**本课分词说明**  
教学脚本用极简分词（英文按 `[a-z0-9_]+` 切，中文按**单字**切）。影响举例：

- 问句 `ERR_CHUNK_42` 会切成 `err`、`chunk`、`42` 三个 token，通常仍能命中含该错误码的段落。
- 但 `chunk_overlap` 会被拆成 `chunk`、`overlap`，无法把 `chunk_overlap` 当作**整体专有词**匹配——生产环境应换分词器。

生产环境建议用 **jieba** 等，并过滤停用词。最小替换示例：

```python
import jieba

def tokenize(text: str) -> list[str]:
    text = text.lower()
    en = re.findall(r"[a-z0-9_]+", text)
    zh = [w for w in jieba.lcut(text) if w.strip() and w not in {"的", "怎么", "什么"}]
    return en + zh
```

跟练阶段可继续用教学版 `tokenize`，理解 BM25 原理即可；**不要原样搬到生产**。

---

### Hybrid Search（混合检索）

**是什么**  
对**同一个问句**，同时跑 **BM25 一路** + **向量一路**，再把两路结果**合成一份**候选列表。

**为什么要两路一起上**  
两路是**互补**的，不是重复劳动：

```text
只有向量  →  口语好，精确代号可能漂（本课 demo：ERR_CHUNK_42 问句 Top-1 曾落到分块参数段）
只有 BM25 →  代号准，口语同义可能漏
Hybrid    →  两路都投票，尽量「又全又准」
```

**类比**  
查资料时既用**全文搜索**（关键词），又用**语义推荐**（「你可能还想看」），最后合并书单。

Hybrid 解决的主要还是**召回阶段**：先尽量把相关段都捞进候选池，还没做最后的精细排序。

---

### RRF（Reciprocal Rank Fusion，倒数排名融合）

**是什么**  
一种**融合多路检索结果**的常用方法：不比较原始分数，只比较**排名第几**。

**为什么需要它**  
BM25 分数可能是 `25.3`，向量距离可能是 `0.89`——**量纲完全不同**，不能直接 `0.5 × BM25 + 0.5 × 向量`。

| 文档 | BM25 分 | 向量距离（cosine） | 若直接加权会怎样？ |
|------|---------|-------------------|------------------|
| A | **25.3** | 0.72 | BM25 数值碾压，可能压过向量里排更前的 B |
| B | 18.7 | **0.55**（距离更小，向量路上更靠前） | 向量认为 B 更相关，但原始分加权可能赢不了 A |

**RRF 怎么做**  
每一路只关心排名。常见公式：

```text
某 chunk 的 RRF 分 = Σ  1 / (k + 在该路的排名)
```

`k` 常取 **60**（平滑常数，避免排名第 1 权重过大；源于 MS MARCO 等评测的常见设定）。该值通常**不敏感**，40～80 均可尝试，跟练固定 60 即可。

**小例子**（两路都排进前几名时）

| chunk | BM25 排名 | 向量排名 | RRF 贡献（k=60） |
|-------|-----------|----------|------------------|
| 错误码段 | 1 | 2 | 1/61 + 1/62 ≈ 0.0325 |
| 分块参数段 | 2 | 1 | 1/62 + 1/61 ≈ 0.0325 |

两路都靠前的段，RRF 分**叠加更高**——这就是「双路都投赞成票」。

**一句话**  
原始分数是各说各话的「地方货币」；**排名**是统一的「投票票」；RRF 用排名做融合。

---

### 召回 vs 精排（先分清阶段）

很多初学者把 Hybrid 和 Rerank 混成一件事。可以记：

| 阶段 | 目标 | 本课对应 | 类比 |
|------|------|----------|------|
| **召回（Recall）** | 宽：尽量别漏相关段 | BM25 + 向量 + RRF | 从书库先抱一摞「可能相关」的书 |
| **精排（Rerank）** | 准：把最相关的顶上去 | CrossEncoder | 专家翻一遍，只留最对口的几本 |

召回可以故意「多捞一点」（例如 20～50 条），允许有点噪声；精排再从里面挑 3～5 条给 LLM，避免上下文被无关段占满。

---

### Rerank（重排 / 精排）

**是什么**  
对已经召回的**候选 chunk 列表**，用更重的模型对每一对 **(问句, chunk)** 打「有多相关」的分，**重新排序**。

**和向量检索的关键区别**

| | 向量检索（Bi-Encoder） | Rerank（Cross-Encoder） |
|--|------------------------|-------------------------|
| 编码方式 | 问句、文档**分开** embed，再比距离 | 问句和文档**拼在一起**进模型，联合 attention |
| 速度 | 快，适合全库百万段 | 慢，只适合对已召回的几十段 |
| 精度 | 粗：语义大致相近即可 | 细：能区分「表面像但其实无关」 |

**输入 / 输出（别和向量搞混）**

- **输入**：问句 + Hybrid 召回的**候选 chunk 正文**（不是向量本身）  
- **输出**：同一批候选的**新排序** + 相关性分数，再取 Top-K 进 Prompt  

**假资料、改写问句都不是最终答案**——进 Prompt 的必须是向量库里**真实 chunk**。

**Cohere Rerank vs 本课 CrossEncoder**

| | Cohere Rerank API | 开源 CrossEncoder（如 ms-marco-MiniLM） |
|--|-------------------|----------------------------------------|
| 能力类型 | Cross-Encoder 精排 | 同为 Cross-Encoder 精排 |
| 部署 | 云端 API，按调用计费 | 本地 GPU/CPU，免 Key |
| 本课选择 | 文档说明等价角色 | 默认实现，方便跟练 |

换成 BGE-Reranker、jina-reranker 等同属**换部署/换模型**；若改成 Bi-Encoder 二次相似度或 LLM 打分，才是**能力类型**变了。

**模型选型提示**：本课 `cross-encoder/ms-marco-MiniLM-L-6-v2` 在 MS MARCO 短问答上表现好，跟练足够。若知识库是**长文档、强领域术语**（法律/医疗/运维手册），可评估 `BAAI/bge-reranker-v2-m3` 等领域 reranker，效果可能更好。

**CANDIDATE_K 是什么**  
先 Hybrid 融合出 Top-N，再交给 Rerank 精排。经验上：

- **N 应明显大于**最终进 Prompt 的 Top-K（例如最终只要 3 条，候选池常取 **20～50**，视库大小与延迟预算而定）。
- **N 太小**：真相关段若排在融合榜第 4，而 `CANDIDATE_K=3`，会被直接裁掉——**精排救不回来**（精排只能重排「已经进池」的段）。
- **N 太大**：CrossEncoder 要对每对 (问句, chunk) 打分，计算量线性上涨。

本课 demo 库只有 3 条 chunk，用 `CANDIDATE_K=5` 或 `3` 仅为演示；你把 `5→3` 若 Top-2 不变，是因为真段本来就在前 3，**不是**说明 3 在生产里也够用。

---

### Top-K 是什么？

检索不会把整库结果都给大模型，只取**排名前 K 条** chunk（如 K=2 或 K=5）。  
K 太大：Prompt 长、噪声多、费 token；K 太小：可能漏掉关键一段。Hybrid 把候选池做大，Rerank 再把最终进 Prompt 的 K 条选准。

---


## 流水线全景

```text
用户问句
  ├─ BM25 召回 ────────┐
  └─ 向量召回 ─────────┼─ RRF 融合 → 候选 Top-N
                       └─ CrossEncoder Rerank → 精排 Top-K → Prompt → LLM
```

---

## 环境准备

**需要**：Python 3.12+、[uv](https://docs.astral.sh/uv/)、可访问 HuggingFace（或已有模型缓存）

```bash
mkdir hybrid-rerank-demo && cd hybrid-rerank-demo
uv init
uv add chromadb langchain langchain-chroma langchain-community \
       langchain-huggingface langchain-text-splitters rank-bm25 sentence-transformers
mkdir -p data
```

---

## 准备知识库 `data/sample.md`

```markdown
# FastAPI 与 RAG 运维笔记

FastAPI 是一个用于构建 API 的 Python Web 框架。

## 分块参数

- **chunk_size**：每块的最大字符数。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 错误码 ERR_CHUNK_42

当向量索引未重建却更新了源文档时，系统可能返回错误码 **ERR_CHUNK_42**。
处理步骤：停止写入 → 清空旧 collection → 重新 embed 全量 chunk → 再开放查询。
```

---

## 第 1 步：共享工具 — 分词、建库、BM25/向量

保存 `step01_keyword_vs_semantic.py`（节选核心）：

```python
from pathlib import Path
import re

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

DATA = Path(__file__).parent / "data" / "sample.md"
PERSIST = Path(__file__).parent / "chroma_db"
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "hybrid_demo"


def load_chunks():
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    return RecursiveCharacterTextSplitter(
        chunk_size=220, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_documents(docs)


def tokenize(text: str) -> list[str]:
    text = text.lower()
    en = re.findall(r"[a-z0-9_]+", text)
    zh = re.findall(r"[\u4e00-\u9fff]", text)
    return en + zh  # 教学用；见名词表「生产分词」jieba 示例


def build_vectorstore(chunks):
    embeddings = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    if PERSIST.exists():
        return Chroma(
            persist_directory=str(PERSIST),
            embedding_function=embeddings,
            collection_name=COLLECTION,
        )
    return Chroma.from_documents(
        chunks, embeddings, persist_directory=str(PERSIST), collection_name=COLLECTION
    )
```

```bash
uv run python step01_keyword_vs_semantic.py
```

对比问法：

- `ERR_CHUNK_42 怎么处理？` → BM25 通常更咬得住代号  
- 口语「前后两段有一点重复」→ 向量通常更稳  

---

## 第 2 步：手撕 BM25

`demo_bm25.py` 核心：

```python
def bm25_search(chunks, query: str, k: int = 3):
    corpus_tokens = [tokenize(c.page_content) for c in chunks]
    bm25 = BM25Okapi(corpus_tokens)
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip(chunks, scores, strict=True), key=lambda x: x[1], reverse=True)
    return ranked[:k]
```

```bash
uv run python demo_bm25.py
```

---

## 第 3 步：Hybrid + RRF

`demo_hybrid_rrf.py` 核心：

```python
def rrf_fuse(ranked_lists, k=60):
    fused = {}
    for ranked in ranked_lists:
        for rank, (content, _score) in enumerate(ranked, start=1):
            fused[content] = fused.get(content, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)
```

```bash
uv run python demo_hybrid_rrf.py
```

---

## 第 4 步：CrossEncoder Rerank

`demo_rerank.py` 核心：

```python
from sentence_transformers import CrossEncoder

CANDIDATE_K = 5   # 粗召回条数
FINAL_K = 2       # 精排后进 Prompt
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

def rerank(query, candidates, model):
    pairs = [[query, text] for text in candidates]
    scores = model.predict(pairs)
    return sorted(zip(candidates, scores, strict=True), key=lambda x: x[1], reverse=True)

# fused = rrf_fuse([bm25, vector])[:CANDIDATE_K]
# reranked = rerank(query, [c for c, _ in fused], CrossEncoder(RERANK_MODEL))
```

```bash
uv run python demo_rerank.py
```

---

## 第 5 步：四档对比

```bash
uv run python demo_pipeline_compare.py
```

对问句 `ERR_CHUNK_42 怎么处理？`，典型现象：

| 档位 | Top-1 常见结果 |
|------|----------------|
| ① 仅向量 | 可能落到「分块参数」❌ |
| ② 仅 BM25 | 「错误码 ERR_CHUNK_42」✅ |
| ③ Hybrid | 错误码段排到前面 ✅ |
| ④ +Rerank | 进一步拉开与噪声段的分数差 ✅ |

这说明：**Hybrid 补向量在精确代号上的短板；Rerank 在候选很接近时再精修顺序。**

---

## 踩过的坑

**1）仅向量对错误码不稳**

`ERR_CHUNK_42` 问句下，向量 Top-1 可能是「chunk_overlap」段——语义上都在讲「分块」，但答非所问。Hybrid 把 BM25 路的正确段抬上来。

**2）BM25 与 Chroma 分数方向相反**

BM25：**越大越好**。Chroma 默认 **cosine 距离**：**越小越好**（不是 L2，除非建库时改过度量）。融合时别直接加权原始分，用 RRF 看排名。

**3）HyDE / 假资料不能当答案（复习）**

Rerank 输入是**候选 chunk 正文**，不是向量；输出是**重排后的 chunk 列表**。

**4）CANDIDATE_K 太小**

教学库只有几条 chunk 时，`5→3` 可能看不出差别。生产里若真段排在融合榜第 4 而 `CANDIDATE_K=3`，会被裁掉——精排「没东西可选」。应让候选池明显大于最终 Top-K（常见 20～50）。

**5）教学分词不是生产分词**

中文按字切只是演示；上线需要 jieba、停用词、领域词典。

**6）HuggingFace SSL 报错**

国内网络可能抖动；模型下载成功后走本地缓存即可。

---

## 工程权衡（面试常问）

| 问题 | 简要答法 |
|------|----------|
| 何时加 Rerank？ | 召回候选多、Top-K 截断敏感、多路分数不可比、准确率优先于延迟 |
| 何时可不加？ | 过滤后只剩几条且已很准；延迟/成本极敏感 |
| Hybrid 够了为何还要 Rerank？ | Hybrid 解决**召回广度**；Rerank 解决**排序精度**（深度交互打分） |
| Cohere vs CrossEncoder？ | 同能力类型；差在 SaaS vs 本地部署 |

---

## 取舍与未做之事

本篇覆盖上游 Day9：**BM25 + Embedding 混合检索，并集成 Reranker**。

- Rerank 默认本地 CrossEncoder，等价 Cohere 精排角色  
- 未展开：Milvus 原生 Hybrid、学习排序、RAGAs 量化评估（后续天）  
- 未挂 HTTP API；CLI 四档对比足够理解原理  

---

## 小结

1. **BM25** 咬关键词；**向量** 懂语义——各有所长。  
2. **Hybrid + RRF** 两路排名融合，解决分数尺度不可比。  
3. **Rerank** 在候选上做 (问句, chunk) 精排，是召回与生成之间的「质量闸门」。  
4. 对 `ERR_CHUNK_42` 类问句，**仅向量可能错 Top-1**；Hybrid 与 Rerank 的价值要在对比里看。  

下一步：RAGAs 评估（Day10–11），用指标证明「加 Hybrid / Rerank 真的更好」。

---

*系列笔记 · Agent 工程跟练 · Week 2 Day 9*
