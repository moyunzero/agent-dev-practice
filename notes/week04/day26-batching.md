# 给 Embedding 和 Rerank 做批处理：一次干一捆，提高吞吐

建索引或精排时，慢往往不是「这一条算得慢」，而是 **每条都单独调一次模型**：每次都付开工费（调度、组 batch、进引擎）。  
把多段文字或多组「问句–文档」捆成一次调用，单位时间内能处理更多条——这就是 **批处理（batching）**。

本文用本地小模型对比：逐条 Embedding vs 一批 Embedding；逐对 Rerank vs 一批 Rerank。并分清它和缓存、异步各解决什么问题。

## 你将会得到什么

1. 说清批处理提升的是吞吐（条/秒），不一定降低「单用户这一问」的延迟  
2. 建库用 `embed_documents`，在线问句用 `embed_query`  
3. Rerank 一批吃的是多组 `(问句, 文档)`，吐出多个分数  
4. 条数太少时一批可能更慢；条数太大一次塞进会 OOM——要找不爆显存/内存的 batch_size  

---

## 零基础名词表

> 建议先读完本节再动手。

### 吞吐量（吞吐）

| 层 | 说明 |
|----|------|
| **是什么** | 单位时间里处理完多少条（文档/秒、配对/秒） |
| **在本文干什么** | 用同一批文本，比较逐条调用和一批调用谁更快做完 |
| **怎么区分** | **单次延迟**是「这一条从进到出多久」；吞吐是「一堆活多久干完」。批处理主攻后者 |

### 固定开销（开工费）

| 层 | 说明 |
|----|------|
| **是什么** | 每次调用几乎都要付的成本：启动、把数据送进模型、调度，与「这一条有多长」关系不大 |
| **在本文干什么** | 逐条 = 付 N 次开工费；一批 = 大致付 1 次，再摊到 N 条上 |
| **怎么区分** | 和「按文本长度真正计算」不同；条数很少时，组一批的成本可能盖过摊薄，逐条看起来也不差 |

### 批次大小（batch_size）怎么找

吞吐一般随 batch 增大而升，但不是越大越好：

```text
太小（如 1～16）→ 开工费占比高，吞吐上不去
合适（常见起点 32～64）→ GPU/CPU 较满、还不爆内存
太大（128+ 视模型和显存）→ 显存/内存溢出（OOM），或算力已饱和，吞吐不再升甚至掉
```

**做法（人话）**：从 **32 或 64** 起步，看任务管理器 / `nvidia-smi` 的显存是否打满、会不会报 OOM；能稳住就略增，一爆就减半。笔记本无独显时，限制往往是 **RAM**，同样用分批，不要一次 `embed_documents(一万条)`。

本文演示脚本只用几十条，一次喂完没问题；**落盘建库**用下面的切片循环。

### Embedding（向量化）

| 层 | 说明 |
|----|------|
| **是什么** | 把一段文字变成一组数字（向量），相近意思的向量更靠近 |
| **在本文干什么** | 对比 `embed_query`（一次一段）和 `embed_documents`（一次一段列表） |
| **怎么区分** | 建库：已经有很多 chunk → 一批文本进、多条向量出。在线检索：通常只有**当前这一句问句** → 用单条 `embed_query` 去搜库 |

### Rerank / CrossEncoder（精排）

| 层 | 说明 |
|----|------|
| **是什么** | 对「问句 + 一篇候选文档」打相关性分数，用来把检索结果再排一次 |
| **在本文干什么** | 对比循环 `predict([(问,文)])` 和一次 `predict([(问,文1), (问,文2), …])` |
| **怎么区分** | **不是**把文档变成向量。一批送进去的是 **多组配对**，出来的是 **多个分数** |

### 批处理 vs 缓存 vs 异步（易混，先对照）

三件事都能让系统「显得快」，刀法不同：

```text
缓存：同一句话再来 → 直接拿出旧答案（少干活）

异步：多个请求同时在等网络/模型
  用户A 等 ─┐
  用户B 等 ─┼─ 等的时候去推进别人（少排队傻等）
  用户C 等 ─┘

批处理：手里已经有一捆要算的东西
  [文1][文2][文3] ──一次调用──► 一起算完（少付多次开工费）
```

| | 缓存 | 异步 | 批处理 |
|--|------|------|--------|
| 前提 | 问句（或 key）会重复 | 同时有多个在等 I/O 的请求 | **已经攒齐**多条要算的输入 |
| 典型 | FAQ、相同问句 | 多用户同时 `/ask`、等 Ollama | 建库 embed；检索后 Top-K **一起** rerank |
| 不优先 | — | 单请求本地狂算 CPU | 用户每次只来一句、还不能等凑批 |

在线、每次不同的一句话：优先考虑缓存（若会重复）或异步（若多人同时等）；**不要**为了批处理硬等凑满一批再答。

### 架构：两条批处理链

```text
Embedding 批
  ["chunk1", "chunk2", …]  ──embed_documents──►  [向量1, 向量2, …]

Rerank 批
  [(问句, 候选1), (问句, 候选2), …]  ──predict──►  [分数1, 分数2, …]
```

---

## 环境准备

- Python 3.12+、[uv](https://github.com/astral-sh/uv)  
- 首次运行会从 Hugging Face 下载两个小模型（需能访问网络；未登录会有 rate limit 提示，一般仍能下）  

`pyproject.toml`：

```toml
[project]
name = "day26-batching"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "langchain-huggingface>=0.1.0",
  "sentence-transformers>=3.0.0",
]
```

```bash
uv sync
```

---

## 步骤 1：玩具直觉——开工费被摊薄

不调真模型：每条假装 `sleep(0.05)` 当固定开销；一批只 sleep 一次。

```python
from __future__ import annotations

import time


def fake_embed_one(text: str) -> int:
    time.sleep(0.05)
    return len(text)


def fake_embed_batch(texts: list[str]) -> list[int]:
    time.sleep(0.05)
    return [len(t) for t in texts]


def main() -> None:
    docs = [f"doc-{i}-" + ("x" * (i % 20)) for i in range(20)]

    t0 = time.perf_counter()
    one_by_one = [fake_embed_one(t) for t in docs]
    t_serial = time.perf_counter() - t0

    t0 = time.perf_counter()
    batched = fake_embed_batch(docs)
    t_batch = time.perf_counter() - t0

    assert one_by_one == batched
    print(f"文档数: {len(docs)}")
    print(f"逐条调用: {t_serial:.2f}s")
    print(f"批处理  : {t_batch:.2f}s")
    print(f"吞吐提升约: {t_serial / t_batch:.1f}x")


if __name__ == "__main__":
    main()
```

```bash
uv run python step01_batch_intuition.py
```

**期望**：逐条约 **1.05s**（20×0.05）；一批约 **0.05s**。这是夸张版，用来建立「少付很多次开工费」的直觉。

---

## 步骤 2：Embedding——`embed_query` vs `embed_documents`

```python
from __future__ import annotations

import os
import time

from langchain_huggingface import HuggingFaceEmbeddings

MODEL = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
N = int(os.getenv("N_DOCS", "32"))

texts = [f"RAG batching demo sentence number {i}." for i in range(N)]


def main() -> None:
    emb = HuggingFaceEmbeddings(model_name=MODEL)
    _ = emb.embed_query("warmup")

    t0 = time.perf_counter()
    one = [emb.embed_query(t) for t in texts]
    t_one = time.perf_counter() - t0

    t0 = time.perf_counter()
    batch = emb.embed_documents(texts)
    t_batch = time.perf_counter() - t0

    print(f"model={MODEL}  docs={N}  dim={len(batch[0])}")
    print(f"逐条 embed_query ×{N}: {t_one:.2f}s  ({N / t_one:.1f} docs/s)")
    print(f"一批 embed_documents : {t_batch:.2f}s  ({N / t_batch:.1f} docs/s)")
    if t_batch > 0:
        print(f"批处理更快约: {t_one / t_batch:.1f}x")


if __name__ == "__main__":
    main()
```

```bash
uv run python step02_embed_batch.py
```

**期望示例**（机器而异）：32 条时一批可到约 **2x** 吞吐。  

**规则（建库）**：一万个 chunk 用 `embed_documents`，并且 **按 batch 切片**，不要一次塞进全部，也不要 `for` + `embed_query`。  
**规则（在线问句）**：只有当前这一句，用 `embed_query`。

万级文本示例（`embed_chunked.py`，可直接复制）：

```python
from langchain_huggingface import HuggingFaceEmbeddings


def embed_documents_chunked(emb, texts: list[str], batch_size: int = 32) -> list:
    out = []
    for i in range(0, len(texts), batch_size):
        out.extend(emb.embed_documents(texts[i : i + batch_size]))
    return out
```

`batch_size` 从 32～64 试起；OOM 就减小。演示用的 `step02` 只有 32 条，才一次性 `embed_documents(texts)`。

条数很少（例如 16）时，一批可能 **并不更快**（组 batch 的开销盖过摊薄）。这不推翻建库用批，只说明：**既要条数够摊薄开工费，又不能单批大到爆内存**。

---

## 步骤 3：Rerank——逐对 vs 一批 `predict`

检索之后，常见是「同一个问句 + Top-K 篇候选」。CrossEncoder 一次可以吃多组配对。

```python
from __future__ import annotations

import os
import time

from sentence_transformers import CrossEncoder

MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
N = int(os.getenv("N_PAIRS", "24"))

query = "What is batching in embeddings?"
pairs = [(query, f"Candidate document about topic {i}.") for i in range(N)]


def main() -> None:
    model = CrossEncoder(MODEL)
    _ = model.predict([pairs[0]])

    t0 = time.perf_counter()
    # CrossEncoder.predict 要的是「配对的列表」；逐对也写成 [p]。
    # 循环里每次 new 一个一元列表，会多一点 Python 分配，基准会略偏「逐对更慢」；
    # 结论（一批仍更快）通常不变。不要改成 predict(p) 除非你确认当前版本接受单元组。
    one = [float(model.predict([p])[0]) for p in pairs]
    t_one = time.perf_counter() - t0

    t0 = time.perf_counter()
    batch = [float(x) for x in model.predict(pairs)]
    t_batch = time.perf_counter() - t0

    print(f"model={MODEL}  pairs={N}")
    print(f"逐对 predict ×{N}: {t_one:.2f}s  ({N / t_one:.1f} pairs/s)")
    print(f"一批 predict     : {t_batch:.2f}s  ({N / t_batch:.1f} pairs/s)")
    if t_batch > 0:
        print(f"批处理更快约: {t_one / t_batch:.1f}x")


if __name__ == "__main__":
    main()
```

```bash
uv run python step03_rerank_batch.py
```

**期望示例**：24 对时一批可到约 **3x**。送进去的是 `(query, doc)` 列表，不是「文档变向量」。

---

## 新手向坑

### 1. 把批处理当成「让这一次用户提问更快」

在线一问一答往往只有一条问句；硬等凑批会 **增加** 等待。批处理服务的是「已经有一捆」。

### 2. 建库却循环 `embed_query`

功能对、速度差。列表一次性（或分批）走 `embed_documents`。

### 3. 条数太少就断言「批处理没用」

先看 32、64 条再下结论；16 条上波动很大。另一头：单批太大 → **OOM**。从 32～64 起步，看显存/内存，找到不爆的最大 batch。

### 4. 一万条直接 `embed_documents(全部)`

演示脚本只有几十条。真建库必须切片（见步骤 2 的 `embed_documents_chunked`），否则笔记本 RAM / 显存可能直接打满。

### 5. Hugging Face 未登录下载慢 / 限速

提示 `HF_TOKEN` 可提高限额；模型需能访问 Hub。也可事先 `huggingface-cli download` 缓存。

---

## 边界：做了什么 / 故意没做什么

**做了**：Embedding 与 Reranker 的逐条 vs 一批对比；和缓存/异步的选用对照；条数太少/单批太大；建库分批循环。

**没做**：自动搜索最优 batch（网格+nvidia-smi）；LangChain `batch` 跑 LLM；vLLM continuous batching；locust 压测。

---

## 小结

| 步骤 | 要点 |
|------|------|
| 地图 | 缓存=少干活；异步=干等切换；批处理=一次干一捆 |
| Embedding | 建库 `embed_documents`；在线问句 `embed_query` |
| Rerank | 一批 `(问, 文)` → 一批分数 |
| 条件 | 条数够才摊薄开工费；单批小到不 OOM（起点常 32～64） |

先分清手里是「一捆活」还是「一群人在等」，再用对刀。
