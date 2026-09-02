# 把 Week1 Naive RAG 升级成 Hybrid + Rerank + Milvus

Week1 的 Naive RAG 已经能跑通：**切分 → Embed → Chroma → 仅向量 Top-K → Prompt → LLM**。  
问「ERR_CHUNK_42 怎么处理？」时，仅靠语义向量，Top-1 却经常偏到「分块参数」段——代号精确匹配弱，口语同义又强，单路检索容易翻车。

本文把同一套文档问答升级成上游 Week2 收官目标要求的形态：**Milvus 存向量 + BM25 与向量混合召回（RRF）+ CrossEncoder Rerank**，再（可选）用 Ollama 生成答案；并提供 **FastAPI `POST /ask`**，对齐 Week1「可调用的 RAG 系统」形态。全文自包含，从空目录可复现。

## 你将会得到什么

1. 说清 Naive 与升级版检索链路差在哪三处  
2. 用 Docker 起 Milvus，把 chunk（含 `text`）写入 collection  
3. 跑通 BM25 ∥ Milvus → RRF → Rerank，并对照仅向量 Top-1  
4. 明白「Milvus 不管 BM25」「RRF 用名次」「生成换的是 contexts」  
5. 用 FastAPI 暴露 `GET /health` 与 `POST /ask`（可用 `generate:false` 只测检索）  
6. 避开：无 text 字段、中文 BM25 分词、把 Rerank 放在召回前；知悉 BM25 预构建、Rerank 中英文模型与 `CANDIDATE_K > FINAL_K`  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按「是什么 → 在本文干什么 → 怎么区分」展开。

### Naive RAG vs 升级 RAG

```text
Naive（Week1）
  文档 → Split → Embed → Chroma → 仅向量 Top-K → Prompt → LLM

升级（本文）
  文档 → Split → Embed → Milvus
                         ↘
  问句 → BM25(chunk 文本) + Milvus 向量 → RRF → Rerank → Prompt → LLM
```

| 环节 | Naive | 升级 |
|------|-------|------|
| 向量库 | Chroma 本地文件 | **Milvus** 独立服务 |
| 召回 | 仅向量 | **BM25 + 向量 → RRF** |
| 排序 | Top-K 即最终 | **Rerank 精排**后再取 FINAL_K |
| 生成 | Prompt + LLM | 同左；变的是 **contexts 质量** |

**候选数 vs 最终数**：`CANDIDATE_K`（进 Rerank 的粗召回条数）应 **大于** `FINAL_K`（塞进 Prompt 的条数）。常见 `FINAL_K` 取 1～3，`CANDIDATE_K` 取 4～20。候选太少，精排没有纠错空间。

### Milvus（向量库）

| 层 | 说明 |
|----|------|
| **是什么** | 生产级向量数据库；Python 用 **pymilvus ≥ 2.4** 的 `MilvusClient`（`create_schema` / `prepare_index_params` 等 API）连 URI |
| **在本文干什么** | 替换 Chroma：存 384 维 embedding + `text`，提供向量 ANN 检索 |
| **怎么区分** | 存的是**向量**（和标量字段），**不做** BM25 关键词打分 |

本文 Docker 镜像锁定 **`milvusdb/milvus:v2.4.15`**，与上述 Client API 对齐。RAG 场景 schema 至少要有：`id`、`text`、`embedding`。没有 `text`，search 只知道「哪条向量近」，拼不了 Prompt。

### BM25（关键词召回）

| 层 | 说明 |
|----|------|
| **是什么** | 经典词袋检索打分：问句与文档共享的词越多、越稀有，分越高 |
| **在本文干什么** | 对**同一批 chunk 原文**在本地建索引；精确命中 `ERR_CHUNK_42` |
| **怎么区分** | 不经过 Milvus；中文教学分词常用「英文词 + 中文按字」 |

**为什么换成 Milvus 后仍要本地 BM25？**  
Milvus 负责语义近邻；关键词打分需要文本词频统计。两条路并行，再融合。

**演示 vs 生产**：下文脚本为简洁，**每次查询都 `BM25Okapi(...)` 重建**——文档很少时没问题。语料变大后应**启动时预构建并常驻内存**（或持久化到 ES/OpenSearch 等），查询只 `get_scores`，避免重复 tokenize。

### RRF（Reciprocal Rank Fusion）

| 层 | 说明 |
|----|------|
| **是什么** | 把多路排序列表按**名次**合成：`分 = Σ 1/(k + rank)` |
| **在本文干什么** | 融合 BM25 排名与 Milvus 向量排名；默认 **k=60** |
| **怎么区分** | **不用**原始 BM25 分或向量 distance 直接相加（量纲不同） |

**k 取多少？** 常见范围大约 1～100。**k 越大**，对排名靠后的候选越「宽容」（尾部名次分差更小）；**k 越小**，更偏爱各路 Top 名次。**60** 是文献与工程里常用的经验默认值，教学直接采用即可，不必一上来调参。

### Rerank（精排）

| 层 | 说明 |
|----|------|
| **是什么** | 对候选 `(query, chunk)` 打相关性分再排序；本文用本地 CrossEncoder |
| **在本文干什么** | 接在 Hybrid **之后**：先宽召回，再精排取 FINAL_K |
| **怎么区分** | 不是召回；放在召回前没有候选可排。角色上等价于 Cohere Rerank，免 API Key |

默认模型 `cross-encoder/ms-marco-MiniLM-L-6-v2` **以英文训练为主**。中文 query + 中文 chunk 仍可跑通演示，但精排质量可能打折。中文/多语场景可换成如 `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` 等（更重、更慢，按机器选型）。

### contexts 与生成

检索输出的 Top-K 正文叫 **contexts**，塞进 Prompt 给 LLM。  
升级主要提高 contexts 是否「问什么给什么」；Ollama 模型可以不变。

---

## 环境准备

- Docker Desktop（Milvus Standalone）  
- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- **版本对齐**：`pymilvus>=2.4.0`；镜像 `milvusdb/milvus:v2.4.15`  
- 可选：[Ollama](https://ollama.com/)（演示生成；没有则只看检索对照）

```bash
mkdir rag-upgrade-demo && cd rag-upgrade-demo
uv init --python 3.12
uv add "pymilvus>=2.4.0" langchain-huggingface langchain-text-splitters \
  rank-bm25 sentence-transformers
mkdir -p data
```

Embedding：`sentence-transformers/all-MiniLM-L6-v2`（**384 维**）。  
Rerank：`cross-encoder/ms-marco-MiniLM-L-6-v2`（英文为主；中文见上文替换建议）。

---

## 样例知识库

保存 `data/sample.md`：

```markdown
# FastAPI 与 RAG 运维笔记

FastAPI 是一个用于构建 API 的 Python Web 框架。它基于类型注解，能自动生成 OpenAPI 文档。

## 分块参数

- **chunk_size**：每块的最大字符数。太小则上下文碎片化；太大则可能超过模型窗口。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 错误码 ERR_CHUNK_42

当向量索引未重建却更新了源文档时，系统可能返回错误码 **ERR_CHUNK_42**。
处理步骤：停止写入 → 清空旧 collection → 重新 embed 全量 chunk → 再开放查询。
该错误码只在运维手册此节出现，不要与 HTTP 422 混淆。

## 小结

加载与分割本身不调用大模型，但决定了后面检索质量的上限。关键词精确匹配与语义相近是两件不同的事。
```

教学问句固定：`ERR_CHUNK_42 怎么处理？` —— 关键词强、仅向量易偏。

---

## 第一步：Docker 启动 Milvus

保存 `docker-compose.yml`（Standalone = etcd + MinIO + milvus；端口 **19531→19530** 避免与本机已有 19530 冲突）：

```yaml
services:
  etcd:
    container_name: day14-milvus-etcd
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: "1000"
      ETCD_QUOTA_BACKEND_BYTES: "4294967296"
      ETCD_SNAPSHOT_COUNT: "50000"
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://etcd:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3

  minio:
    container_name: day14-milvus-minio
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    ports:
      - "9010:9000"
      - "9011:9001"
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  standalone:
    container_name: day14-milvus-standalone
    image: milvusdb/milvus:v2.4.15
    command: ["milvus", "run", "standalone"]
    security_opt:
      - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - milvus_data:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 3
    ports:
      - "19531:19530"
      - "9092:9091"
    depends_on:
      etcd:
        condition: service_healthy
      minio:
        condition: service_healthy

volumes:
  etcd_data:
  minio_data:
  milvus_data:
```

> **etcd**：`advertise-client-urls` 必须是 Compose 网络内可路由的 **`http://etcd:2379`**，不要写 `127.0.0.1`。  
> 亦可对照 [Milvus 官方 Standalone Docker](https://milvus.io/docs/install_standalone-docker.md)。

```bash
docker compose up -d
docker compose ps   # standalone 应为 healthy
```

配置：

```python
# milvus_config.py
import os
MILVUS_URI = os.getenv("MILVUS_URI", "http://127.0.0.1:19531")
COLLECTION = "day14_rag_upgrade"
DIM = 384
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
```

---

## 第二步：索引入库（必须带 text）

```python
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import DataType, MilvusClient
from milvus_config import COLLECTION, DIM, EMBED_MODEL, MILVUS_URI

client = MilvusClient(uri=MILVUS_URI)
if client.has_collection(COLLECTION):
    client.drop_collection(COLLECTION)

schema = MilvusClient.create_schema(auto_id=False)
schema.add_field("id", DataType.INT64, is_primary=True)
schema.add_field("text", DataType.VARCHAR, max_length=4096)
schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=DIM)
index_params = client.prepare_index_params()
index_params.add_index("embedding", index_type="AUTOINDEX", metric_type="COSINE")
client.create_collection(COLLECTION, schema=schema, index_params=index_params)

chunks = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=40).split_text(
    Path("data/sample.md").read_text(encoding="utf-8")
)
model = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
vectors = model.embed_documents(chunks)
rows = [{"id": i + 1, "text": chunks[i], "embedding": vectors[i]} for i in range(len(chunks))]
client.insert(COLLECTION, rows)
client.flush(COLLECTION)  # 立刻 search 时建议 flush，保证可见
print("indexed", len(rows))
```

**要点**：

- `dim` 必须与 Embedding 模型一致（384）。  
- **`flush`**：把缓冲刷到可持久化/可检索状态。教学脚本 **insert 后立刻 search**，建议显式 `flush`。小数据量、稍后才查时，服务端也会自动落盘，但「刚写完就查」仍以 flush（或确认一致性）更稳。

---

## 第三步：Hybrid — BM25 ∥ Milvus → RRF

```python
import re
from rank_bm25 import BM25Okapi

def tokenize(text: str) -> list[str]:
    text = text.lower()
    return re.findall(r"[a-z0-9_]+", text) + re.findall(r"[\u4e00-\u9fff]", text)

def bm25_ranked(chunks: list[str], query: str):
    # 演示：每次重建。生产：启动时 BM25Okapi 一次，查询复用实例
    bm25 = BM25Okapi([tokenize(c) for c in chunks])
    scores = bm25.get_scores(tokenize(query))
    return sorted(zip(chunks, map(float, scores)), key=lambda x: x[1], reverse=True)

def milvus_ranked(client, model, query: str, n: int):
    hits = client.search(
        COLLECTION, data=[model.embed_query(query)], limit=n, output_fields=["text"]
    )[0]
    return [(h["entity"]["text"], float(h["distance"])) for h in hits]

def rrf_fuse(lists, k=60):
    # k=60：经验默认；越大对尾部名次越宽容
    fused = {}
    for ranked in lists:
        for rank, (content, _) in enumerate(ranked, 1):
            fused[content] = fused.get(content, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda x: x[1], reverse=True)

query = "ERR_CHUNK_42 怎么处理？"
bm25 = bm25_ranked(chunks, query)
vector = milvus_ranked(client, model, query, n=len(chunks))
hybrid = rrf_fuse([bm25, vector])
print("BM25 top1:", bm25[0][0][:40])
print("Vector top1:", vector[0][0][:40])
print("Hybrid top1:", hybrid[0][0][:40])
```

**典型现象**：仅向量 Top-1 偏「分块参数」；BM25 / Hybrid Top-1 落到「错误码 ERR_CHUNK_42」。

---

## 第四步：Rerank +（可选）生成

```python
from sentence_transformers import CrossEncoder

FINAL_K = 2       # 最终进 Prompt 的条数（常见 1～3）
CANDIDATE_K = 4   # 进 Rerank 的候选；必须 > FINAL_K
ce = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
# 中文为主时可换：cross-encoder/mmarco-mMiniLMv2-L12-H384-v1
candidates = [c for c, _ in hybrid[:CANDIDATE_K]]
scores = ce.predict([[query, c] for c in candidates])
reranked = sorted(zip(candidates, map(float, scores)), key=lambda x: x[1], reverse=True)
contexts = [c for c, _ in reranked[:FINAL_K]]
```

对照三档：

| 档 | 做法 |
|----|------|
| ① Naive | 仅 Milvus Top-K |
| ② Hybrid | RRF 后 Top-K |
| ③ Upgraded | Hybrid 候选再 Rerank |

**小实验**：`FINAL_K=1` 时，① 仍可能是分块参数段；②/③ Top-1 应为错误码段——混合召回把关键词路拉回来了。

### 可选：Ollama 最小生成

```python
import json
import urllib.request

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen2:7b"

ctx = "\n\n".join(f"[{i}] {c}" for i, c in enumerate(contexts, 1))
prompt = (
    "只根据下列上下文回答问题；上下文没有的信息就说不知道。\n\n"
    f"上下文:\n{ctx}\n\n问题: {query}\n答案:"
)
body = json.dumps(
    {"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
    ensure_ascii=False,
).encode()
req = urllib.request.Request(
    f"{OLLAMA_URL}/api/generate",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=120) as resp:
    answer = json.loads(resp.read().decode()).get("response", "")
print(answer)
```

模型可与 Week1 相同；**变的是 contexts**。未起 Ollama 则跳过本段即可。

---

## 常见坑

### 1. Collection 没有 `text`

只能拿到 id/distance，Hybrid/Rerank/Prompt 都缺正文。

### 2. 中文 BM25 全 0 分

`\w` 切不好中文。教学用：英文 `[a-z0-9_]+` + 中文按字 `[\u4e00-\u9fff]`。

### 3. RRF 误用「原始分数相加」

BM25 与向量 distance 不可比；RRF 只看名次。

### 4. 把 Rerank 放在召回前

没有候选可排；顺序必须是 **召回 →（融合）→ 精排**。

### 5. 以为换 Milvus 就自动有 Hybrid

Milvus 只换向量库；BM25 + RRF + Rerank 仍要自己接。

### 6. etcd advertise 写成 127.0.0.1

Compose 网络内应 advertise 服务名 `etcd`，否则 standalone 可能连不上元数据服务。

### 7. pymilvus / 镜像版本过旧

`MilvusClient.create_schema`、`prepare_index_params` 需要 **2.4+**；请锁 `pymilvus>=2.4.0` 与 `milvus:v2.4.15`（或同系列）。

### 8. `CANDIDATE_K <= FINAL_K`

精排几乎无法纠错；保持候选池明显大于最终条数。

---

## 封成 FastAPI：对齐 Week1「系统」形态

CLI 能证明三件套会跑；**系统**还要能被 HTTP 调用（与 Week1 `POST /ask` 同级）。

索引与 Compose 就绪后：

```bash
uv run uvicorn main_api:app --reload --port 8014
```

```bash
curl -s http://127.0.0.1:8014/health
# {"status":"ok","service":"day14-upgraded-rag"}

curl -s -X POST http://127.0.0.1:8014/ask \
  -H 'Content-Type: application/json' \
  -d '{"question":"ERR_CHUNK_42 怎么处理？","generate":false}'
```

响应里的 `pipeline: milvus+bm25/rrf+rerank` 表示检索仍是三件套；`generate:false` 时 `answer` 为 `(retrieve-only)`，便于先验收 API。本机有 Ollama 时把 `generate` 设为 `true` 即可生成答案。

核心文件：`upgraded_pipeline.py`（检索+可选生成）、`main_api.py`（路由）。

---

## 边界：做了什么 / 故意没做什么

**做了**：Naive → Milvus + Hybrid(RRF) + CrossEncoder Rerank；固定问句对照；可选 Ollama 生成；Compose 自包含；**FastAPI `/health` + `/ask`**。

**没做**：再嵌 Multi-Query/HyDE；全量 RAGAs 评测；Milvus 原生 Hybrid；BM25 生产级持久化。

---

## 小结

| 步骤 | 动作 |
|------|------|
| 换库 | Chroma → Milvus（带 `text`，v2.4+） |
| 加召回 | BM25 ∥ 向量 → RRF（名次，k≈60） |
| 加精排 | CrossEncoder Rerank（`CANDIDATE_K > FINAL_K`） |
| 生成 | Prompt + LLM；升级 contexts |
| 系统形态 | FastAPI 暴露升级后的 `/ask` |

Week2 收官不是推倒重来，而是把已学模块**串进同一条检索链**，并尽量保持与 Week1 一样可调用的服务入口。仅向量不够稳时，先让关键词路进候选，再用精排把最终 contexts 排准。
