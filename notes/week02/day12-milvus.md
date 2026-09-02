# 用 Docker 部署 Milvus 并跑通 Python SDK：从 Chroma 到生产级向量库

Week1 用 **Chroma** 在本地文件里建索引、做 Top-K 检索，Naive RAG 半链路已经跑通。数据量上到百万、千万条，或要多服务共享同一套向量库时，Chroma 的「嵌进 Python 进程 / 单机文件」就不够用了。

**Milvus** 是独立部署的向量数据库：Docker 起服务，Python 用 **pymilvus** 做增删改查和 ANN 搜索。本文在单机 **Standalone** 模式下完成：**Compose 部署 → 建 collection → insert / search / delete → 与 RAG 检索半链路串联**。全文自包含，按步骤复制即可复现。

## 你将会得到什么

1. 说清 Milvus 与 Chroma 各适合什么阶段，Standalone 里 etcd / MinIO 各干什么  
2. 用 Docker Compose 启动 Milvus，并用脚本验证连接  
3. 用 **MilvusClient** 完成 collection 创建、向量 CRUD、Top-K 检索  
4. 把同一套 RAG 半链路（切分 → embed → 存 → 搜）从 Chroma 换到 Milvus，并理解为何要存 `text` 字段  
5. 避开端口冲突、`id_type`、dim 不一致、忘记 `flush` 等常见坑  

---

## 零基础名词表

> 本篇会用到向量库、Milvus、pymilvus、Docker 等词。若你刚接触 RAG，建议先读完本节再动手；每个词都尽量用「它是什么 → 在本文干什么 → 和别的东西怎么区分」来讲。

### Embedding 与向量：为什么 RAG 要「向量化」？

LLM 读不懂原始 Markdown 文件里的几万字；检索阶段也不能逐字比对「哪段最像你的问句」。常见做法是：

1. 把每段文本（**chunk**）送进 **Embedding 模型**，输出一串数字，例如 384 个浮点数 —— 这叫 **向量（vector）**。
2. 语义相近的文本，向量在空间里 **距离更近**（例如都讲 FastAPI 路由的两段，比「讲错误码」的那段更近）。
3. 用户问句同样 embed 成向量，在库里找 **距离最近的几段** —— 这就是 **Top-K 检索**。

本文用的模型是 **`all-MiniLM-L6-v2`**，输出 **384 维**向量。后面建 Milvus collection 时，`dim` 必须等于 384，否则 insert 会报错。

### 向量库在 RAG 半链路里干什么？

完整 RAG 很长；本文只做到 **检索半链路**（还没接 LLM 生成答案）：

```text
离线（建索引，可 nightly 跑）：
  原始文档 → 切分 chunk → Embedding → 写入向量库

在线（用户提问时）：
  用户问句 → embed 成 query 向量 → 向量库 Top-K → 取回 chunk 正文 →（Day5+）拼 Prompt → LLM 生成
```

**向量库的职责**只有两件事：**持久化存向量**（以及你定义的 id、text 等字段），**按相似度做近似最近邻搜索（ANN）**。  
它不负责切分文档、不负责调用 LLM、不负责拼 Prompt。换 Milvus 只换「存和搜」的后端；Loader、Splitter、Embed 模型可以不变。

### ANN 搜索与 Index：为什么不能暴力算距离？

若有 100 万条向量，问句来了后对每条算一遍距离，太慢。**ANN（Approximate Nearest Neighbor，近似最近邻）** 用索引结构（如 HNSW、IVF）跳过大量无关向量，用「略损精度换速度」的方式快速返回 Top-K。  
Milvus 在 **向量字段** 上建 **Index**；本文用 MilvusClient 简版 API 时默认 **AUTOINDEX + COSINE**，教学够用。Scalar 字段（如 `text`）也可建普通过滤索引，但 ANN 索引是 Milvus 的核心。

### Chroma vs Milvus：各适合什么阶段？

| 维度 | Chroma | Milvus |
|------|--------|--------|
| **定位** | 轻量嵌入式向量库，和 LangChain 集成快 | **生产级**向量数据库，可独立集群部署 |
| **典型阶段** | 本地原型、教学 demo、百万条以下验证 | 数据量更大、要多服务共享、要独立扩缩容的生产环境 |
| **部署** | `pip install`，数据落本地目录 `chroma_db/` | **Docker / K8s 独立服务**，Python 通过 URI 远程连接 |
| **进程模型** | 常嵌在业务 Python 进程或单机文件 | 检索与业务 **进程隔离**，ANN 吃 CPU/内存时不拖垮 API |
| **概念** | collection 为主 | collection + **field schema** + **index** +（可选）partition |
| **运维** | 几乎零配置 | 需关心 etcd、对象存储、健康检查、备份 |

**生产环境为什么常把向量库独立部署？** 简要四条：

1. **资源隔离**：ANN 检索是计算密集型，独立出来避免和业务 API 抢 CPU/内存。  
2. **弹性扩缩**：向量数据增长快，可单独加 Query Node / Index Node，不必整体扩容业务服务。  
3. **多服务共享**：同一 Milvus 集群可同时服务 RAG、推荐、语义搜索等多条业务线。  
4. **专业化运维**：索引类型、分片、compaction、备份快照等有专门玩法，独立部署便于专人维护。

教学阶段 Chroma 足够；当你要模拟「上线后向量库怎么跑」，Milvus Standalone 是最小的一步。

### Milvus 核心概念（与关系型数据库对照）

| Milvus | 含义 | 类比 RDBMS |
|--------|------|------------|
| **Collection** | 逻辑上的一组 Entity，共享同一套 Field 定义与索引策略 | **Table（表）** |
| **Field** | 一列数据的类型与约束 | **Column（列）** |
| **Entity** | 一条完整记录（一个 id + 若干 field 值） | **Row（行）** |
| **Index** | 建在字段上的索引；向量 Field 上是 **ANN 索引** | **Index**（但语义特指向量近似搜索） |
| **Partition** | Collection 内的逻辑子集，按规则划分数据 | **Partition 表 / 分区** |

**Field 的三种常见角色**（读 schema 时先认类型）：

| 类型 | 例子 | 说明 |
|------|------|------|
| **Primary Key** | `id` | 唯一标识一行；本文 `auto_id=False`，insert 时自己传 id |
| **Vector Field** | `embedding`，dim=384 | Milvus 特有；search 在这一列上做 ANN |
| **Scalar Field** | `text`（VARCHAR）、`source`（VARCHAR） | 普通标量列；可 `output_fields` 取回，也可做过滤（本文未展开 filter） |

**Collection 不止「列定义」**：还包含分片策略、一致性级别、索引参数等元信息。教学脚本用 MilvusClient 简版 API 时这些有默认值；生产调优再深入。

### pymilvus 与 MilvusClient：Python 怎么连上 Milvus？

**Milvus** 是服务端；**pymilvus** 是官方 Python SDK。  
本文用 **MilvusClient**（高层 API）：一个 URI 连上服务，直接 `create_collection` / `insert` / `search` / `delete`，适合 Standalone 教学。旧版 ORM 风格 `connections.connect` + `Collection` 仍存在于文档，但新项目优先 MilvusClient。

连接串示例：`http://127.0.0.1:19531` —— 表示本机 Docker 映射的 gRPC/HTTP 端口（容器内通常是 19530）。

### Insert / Flush / Search / Delete：四个动词各干什么？

| 操作 | 干什么 | 忘记会怎样 |
|------|--------|------------|
| **insert** | 把 Entity（id、embedding、可选 text）写入 Milvus | 库里没数据，search 空结果 |
| **flush** | 把内存缓冲 **刷到持久化存储**，对后续 search 可见 | 刚 insert/delete 的数据 **可能搜不到或仍被搜到**，结果不稳定 |
| **search** | 传入 **query 向量**（不是原始字符串），返回 Top-K + distance + 你请求的 `output_fields` | 问句必须先 `embed_query` |
| **delete** | 按主键 id 删除 Entity | 已删 id **不会**再出现在 Top-K 里；同样建议 delete 后 **flush** |

**dim 约束**：insert 时每条 `embedding` 的长度必须等于建表时的 `dim`（本文 384）。换 Embedding 模型往往要 **重建 collection + 全量 re-embed**。

**`output_fields`**：`search` 默认只给 id 和 distance。RAG 要拼 Prompt，必须加 `output_fields=["text"]`（或你定义的别的 scalar 字段），否则只知道「哪条向量近」，拿不到正文。

### 两种 Collection 设计：练 CRUD vs 做 RAG

| | 只有 `id + embedding` | 还有 `text` 标量字段 |
|--|----------------------|---------------------|
| **用途** | 理解 insert/search/delete | 完整 RAG 检索半链路 |
| **search 后** | 只有 id，正文要靠脚本内存里的 list | 直接从 Milvus 取回 chunk 文本 |
| **服务重启** | 只剩向量，**正文丢失**（若没别处存） | 正文仍在 Milvus，可继续检索 |

生产 RAG **必须**把可展示的正文（或 source、page）存进 scalar field；只存向量不够。

### Standalone 架构：etcd 与 MinIO 各负责什么？

Milvus Standalone 不是「一个二进制打天下」，至少依赖两个外部组件：

```text
你的 Python (pymilvus)
        ↓ URI（如 http://127.0.0.1:19531）
Milvus Standalone 进程
   ├── etcd     — 元数据与协调
   └── MinIO    — 向量与索引的对象存储
```

**etcd — 元数据存储（Metadata Store）**

| 存什么 | 举例 |
|--------|------|
| Schema | 有哪些 Collection、Field 叫什么、dim 多少 |
| 拓扑与协调 | 组件注册、任务调度、Channel 分配（集群版更明显） |
| 运行时配置 | 部分配置的持久化与同步 |

可粗类比：RDBMS 的 **系统目录（System Catalog）** + **服务注册中心**。Milvus 重启后仍知道「有哪些表、列长什么样」。

**MinIO — 对象存储（Object Storage）**

| 存什么 | 举例 |
|--------|------|
| 数据文件 | insert 落盘的 segment / binlog |
| 索引文件 | 建好的 ANN 索引 |
| 快照与中间结果 | compaction、import 等产生的文件 |

可粗类比：RDBMS 的 **数据文件** + **WAL/Redo**。向量体积大，不能指望全放 Milvus 进程内存；MinIO 负责 **大块数据的持久化**。

**为什么教学 Standalone 也要它们？** 进程重启后元数据与海量向量不丢；且与分布式版 **数据格式一致**，以后加 Node 扩集群不必推倒重来。

---

## 环境准备

- **Docker Desktop** 已安装并启动  
- **Python ≥ 3.12**，包管理器任选（下文用 `uv`；`pip` 同理）  
- 依赖：`pymilvus`、`langchain-huggingface`、`langchain-text-splitters`、`sentence-transformers`  

```bash
mkdir milvus-rag-demo && cd milvus-rag-demo
uv init
uv add pymilvus langchain-huggingface langchain-text-splitters sentence-transformers
```

Embedding 模型与 Week1 一致：**`sentence-transformers/all-MiniLM-L6-v2`**，输出 **384 维**向量。

---

## 第一步：Docker Compose 启动 Milvus

创建 `docker-compose.yml`（基于 [Milvus 官方 Standalone 文档](https://milvus.io/docs/install_standalone-docker.md)，并修正 etcd 在 Docker 网络内的 advertise 地址；端口可按需改）：

```yaml
services:
  etcd:
    container_name: day12-milvus-etcd
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
    container_name: day12-milvus-minio
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
    container_name: day12-milvus-standalone
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

> **etcd 为何用 `http://etcd:2379` 而不是 `127.0.0.1`？**  
> `advertise-client-urls` 是 etcd 告诉客户端「我对外可达的地址」。若写死 `127.0.0.1`，Milvus 容器（不在 etcd 容器内）连上后可能被指回 **自己容器内的 localhost**，导致 etcd 连接失败、`standalone` 健康检查红。Compose 网络内应写 **服务名 `etcd`**。  
> Milvus 官方示例里有时仍写 `127.0.0.1`，在部分环境能侥幸跑通（首连走 `ETCD_ENDPOINTS` 环境变量），但跨机器/慢启动时更容易翻车，教学 compose 建议按上表写。

> **MinIO 凭据**：本文锁定的镜像 `RELEASE.2023-03-20` 仍支持 `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`。若自行升级到较新 MinIO，需改用 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`。

```bash
docker compose up -d
docker compose ps   # standalone 状态应为 healthy
```

**期望**：三个容器 `Up`，`day12-milvus-standalone` 为 `healthy`。Milvus gRPC 在宿主机 **19531**（映射容器内 19530）。

连通性检查 `check_milvus.py`：

```python
from pymilvus import MilvusClient

MILVUS_URI = "http://127.0.0.1:19531"

client = MilvusClient(uri=MILVUS_URI)
print("Milvus 版本:", client.get_server_version())
print("Collections:", client.list_collections())
```

```bash
uv run python check_milvus.py
# Milvus 版本: v2.4.15
# Collections: []
```

---

## 第二步：创建 Collection

MilvusClient 简版 API：声明 collection 名、向量维度、主键字段即可。

```python
from pymilvus import MilvusClient

MILVUS_URI = "http://127.0.0.1:19531"
COLLECTION = "rag_demo"
DIM = 384

client = MilvusClient(uri=MILVUS_URI)

if client.has_collection(COLLECTION):
    client.drop_collection(COLLECTION)

client.create_collection(
    collection_name=COLLECTION,
    dimension=DIM,
    auto_id=False,
    primary_field_name="id",
    id_type="int",              # pymilvus 3.x 用 "int"，不是 "int64"
    vector_field_name="embedding",
)

print("已创建:", client.list_collections())
```

**要点**：`DIM=384` 必须与 Embedding 模型输出一致；`auto_id=False` 表示 insert 时自己传 `id`。

---

## 第三步：Insert / Search / Delete

示例数据 `data/sample.md`（两段内容，切分后约 2 个 chunk）：

```markdown
# FastAPI 与 RAG 运维笔记

## 分块参数
- **chunk_size**：每块的最大字符数…
- **chunk_overlap**：相邻块重叠字符数…

## 错误码 ERR_CHUNK_42
当向量索引未重建却更新了源文档时，系统可能返回 ERR_CHUNK_42。
处理：停止写入 → 清空 collection → 重新 embed → 再开放查询。
```

CRUD 脚本核心逻辑：

```python
from pathlib import Path
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymilvus import MilvusClient

MILVUS_URI = "http://127.0.0.1:19531"
COLLECTION = "rag_demo"
DIM = 384
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

def main():
    client = MilvusClient(uri=MILVUS_URI)
    text = Path("data/sample.md").read_text(encoding="utf-8")
    chunks = RecursiveCharacterTextSplitter(
        chunk_size=220, chunk_overlap=40
    ).split_text(text)

    model = HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    vectors = model.embed_documents(chunks)
    assert len(vectors[0]) == DIM

    rows = [{"id": i + 1, "embedding": vectors[i]} for i in range(len(chunks))]
    client.insert(collection_name=COLLECTION, data=rows)
    client.flush(COLLECTION)   # 刷盘，后续 search 才稳定

    query = "ERR_CHUNK_42 怎么处理？"
    q_vec = model.embed_query(query)
    hits = client.search(
        collection_name=COLLECTION,
        data=[q_vec],
        limit=2,
        output_fields=["id"],
    )[0]
    for hit in hits:
        print(hit["id"], hit["distance"])

    client.delete(collection_name=COLLECTION, ids=[1])
    client.flush(COLLECTION)
```

**三个必记点**：

1. **insert 的向量 dim = schema 的 dim**，否则报错  
2. **`insert` / `delete` 后 `flush`**，否则可能搜不到新数据或仍搜到已删 id  
3. **`search` 传入的是 query 向量**，不是原始字符串；要先 `embed_query`  

此 schema 只有 `id + embedding`，打印正文只能靠内存里的 `chunks` 列表——适合练 CRUD，**不适合**生产 RAG（服务重启后正文丢失）。

---

## 第四步：RAG 半链路串联（带 text 字段）

与 Chroma 版 Day4 对照：

| Day4 (Chroma) | Milvus |
|---------------|--------|
| `TextLoader` | `Path.read_text` |
| `RecursiveCharacterTextSplitter` | 同款 |
| `HuggingFaceEmbeddings` | 同款 (384 dim) |
| `Chroma.from_documents` | `insert` + `flush` |
| `similarity_search_with_score` | `client.search` + `output_fields` |

RAG 场景要在 collection 里加 **`text` 标量字段**，search 时一并取回：

```python
from pymilvus import MilvusClient, DataType

schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=False)
schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=4096)
schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=384)

index_params = client.prepare_index_params()
index_params.add_index(
    field_name="embedding",
    index_type="AUTOINDEX",
    metric_type="COSINE",
)
client.create_collection(
    collection_name="rag_pipeline",
    schema=schema,
    index_params=index_params,
)

rows = [
    {"id": i + 1, "text": chunks[i], "embedding": vectors[i]}
    for i in range(len(chunks))
]
client.insert(collection_name="rag_pipeline", data=rows)
client.flush("rag_pipeline")

hits = client.search(
    collection_name="rag_pipeline",
    data=[q_vec],
    limit=2,
    output_fields=["text"],   # 不带 text，RAG 拼不了 Prompt
)[0]
for hit in hits:
    print(hit["entity"]["text"][:80])
```

Top-K 的 `text` 可直接塞进 Day5 的 Prompt；LLM 生成与向量库无关。

**小改动观察**：库中只有 2 条 chunk 时，把 `limit=5` 改成 Top-5，**最多仍只返回 2 条**——Milvus 不会凑数；要更多结果，得先 insert 更多 chunk。

---

## 常见坑

### 1. etcd `advertise-client-urls` 写成 `127.0.0.1`

**现象**：`standalone` 起不来或 healthcheck 一直红，日志里 etcd 连接失败。  
**原因**：Milvus 在独立容器里，etcd 若对外宣称「我在 127.0.0.1」，客户端会被指到错误地址。  
**处理**：改为 `http://etcd:2379`（Compose 服务名，见上文 compose 块）。

### 2. 端口 19530 已被占用

本机若已有 Milvus，Compose 可映射到 **19531**，客户端 URI 改为 `http://127.0.0.1:19531`。

### 3. `Connection refused`

Docker Desktop 未启动，或 `standalone` 尚未 `healthy`。先 `docker compose ps`，再等 healthcheck 通过。

### 4. `id_type="int64"` 报错

pymilvus 3.x 的 MilvusClient 简版建表用 **`"int"`**，不是 `"int64"`。

### 5. 忘记 `flush`

insert/delete 后不调 `flush`，search 结果可能滞后或不符合预期。

### 6. RAG 只存向量不存 text

只有 `id + embedding` 时，检索只知道「哪条向量近」，拿不到正文；必须在 schema 里加 `text`（或 source 等 metadata），并用 `output_fields` 取回。

### 7. HuggingFace 加载时的 gRPC 警告

终端里 `FD from fork parent still in poll list` 多为模型 fork + gRPC 的噪音，一般可忽略；不影响 Milvus 读写。

---

## 今日边界

**做了**：Docker Standalone 部署；MilvusClient 建表、CRUD、Top-K；RAG 半链路与 Chroma 对照；384 维 + COSINE。

**没做**（留给后续）：Milvus 集群分片、Hybrid 原生融合、Zilliz Cloud、LangChain 全量 Milvus 封装、RBAC。Hybrid / Rerank 与 Milvus 深度整合可在 Advanced RAG 阶段再串。

---

## 小结

| 步骤 | 动作 |
|------|------|
| 部署 | `docker compose up -d`，等 standalone healthy |
| 建表 | `create_collection`，dim 与 Embedding 一致 |
| 写入 | `insert` + `flush`，RAG 场景带上 `text` |
| 检索 | 问句 embed → `search` + `output_fields` |
| 删除 | `delete(ids=...)` + `flush` |

Milvus 换的是向量库的 **存和搜**；Loader、Splitter、Embed、Prompt、LLM 链路不变。原型用 Chroma 够快；要上规模、要隔离、要多服务共享，独立部署 Milvus 是常见下一步。
