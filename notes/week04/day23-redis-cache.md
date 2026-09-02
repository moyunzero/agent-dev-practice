# 给 Agent 加 Redis 缓存：别让相同问句重复问模型

性能画像若显示墙钟时间多半花在「等大模型」，下一刀往往不是再抠本地小工具，而是：**相同问句别再跑一遍 Agent / LLM**。  
本文用 **Redis** 缓存 **LLM（Agent）最终响应**：第一次 `miss` 正常调用模型；第二次同一问句 `hit`，直接返回缓存，延迟可从数十秒降到亚毫秒级。

## 你将会得到什么

1. 说清 Redis 缓存与数据库、向量库的差别  
2. 用 Docker 起 Redis，跑通 `GET` / `SET` + TTL、命中与未命中  
3. 给带工具的 Agent（LangChain `create_agent` + Ollama）加上「先查缓存、再调模型」  
4. 同问句对比优化前后延迟；理解为何优先缓存「最终回答」而不是只缓存检索结果  

---

## 零基础名词表

> 建议先读完本节再动手。

### 缓存（Cache）

| 层 | 说明 |
|----|------|
| **是什么** | 把「算过一次、短期内还会再用」的结果暂存起来，下次用钥匙直接取，避免重算 |
| **在本文干什么** | 把 Agent 对某句问话的**最终回答**存进 Redis；同一问句再来时跳过模型 |
| **怎么区分** | 缓存可以丢（再算一遍即可）；数据库是业务真相源，丢了会出事 |

类比：便签板上写「这道题答案是 15」——同事再问同一道题，念便签即可，不必再算。

### Redis

| 层 | 说明 |
|----|------|
| **是什么** | 常驻**内存**的键值（key-value）存储，读写极快，常被用作缓存 |
| **在本文干什么** | 存 `问句对应的 key → 最终回答字符串`，并设置过期时间（TTL） |
| **怎么区分** | 不是向量库（不按语义相似检索）；不是关系库（不以 SQL 管复杂表为主） |

**本文用到的几个操作：**

| 操作 | 干什么 | 忘了 / 用错会怎样 |
|------|--------|-------------------|
| `PING` | 确认连上 Redis | 连不上则后续全失败 |
| `GET key` | 按钥匙读 | 没有则返回空（本文当 miss） |
| `SET key value EX 秒` | 写入并设过期 | 不设 EX 可能永久占内存；写错 key 等于缓存「串台」 |
| `TTL key` | 看还剩多少秒 | `-2` 表示 key 已不存在 |
| `DEL key` | 删掉缓存 | 下次必 miss，适合做「无缓存 vs 有缓存」对比 |

### key / value / TTL

| 词 | 是什么 | 在本文干什么 |
|----|--------|--------------|
| **key** | 钥匙，字符串 | 用问句的 SHA256 截断生成，如 `day23:llm:d919b861c749ba54` |
| **value** | 存进去的内容 | Agent 最终回答文本（不是工具中间返回值） |
| **TTL** | Time To Live，多久过期 | 例如 300 秒后自动删除，避免答案永久陈旧、内存涨满 |

问句改一个字 → 哈希变 → **新 key** → 当作没见过的问题（miss）。

### HIT 与 MISS

| | **MISS（未命中）** | **HIT（命中）** |
|--|-------------------|-----------------|
| **是什么** | Redis 里没有这把钥匙 | 有，直接读出 value |
| **在本文干什么** | 调用 Agent / Ollama，再 `SET` | **不**调用 Agent，返回缓存 |
| **体感** | 慢（常见十几～几十秒） | 极快（常显示 `0.00s`） |

### 检索缓存 vs 响应缓存（易混，务必分清）

RAG / Agent 链路里至少有两段「贵」的地方：

```text
用户问句
   ↓
① Embedding + 向量检索     ← 找资料
   ↓
② Prompt + LLM / Agent    ← 生成最终答案
   ↓
最终回答
```

| 缓存对象 | 人话 | 跳过哪一段 | 省多少 |
|----------|------|------------|--------|
| **检索缓存** | 别重复找资料 | 主要是 ① | 有用，但 ② 往往仍要跑 |
| **响应缓存（本文重点）** | 别重复问模型 | **①② 都可跳过**（同问句直接返回） | **最大**（上游目标：缓存 LLM 响应） |

一句话：**检索缓存 = 别重复找资料；响应缓存 = 别重复问模型。**

### Agent（本文范围）

| 层 | 说明 |
|----|------|
| **是什么** | 大模型按「思考 → 调工具 → 观察 → 再答」循环完成任务的程序 |
| **在本文干什么** | 用 `create_agent` + `get_word_length` / `add` + Ollama，产出最终回答，再被 Redis 缓存 |
| **怎么区分** | 缓存的是**整轮结束后的最终文本**，不是某一次工具返回的数字 |

### 架构对照

```text
无缓存：
  问句 ──► Agent(Ollama+工具) ──► 回答     （每次都慢）

有缓存：
  问句 ──► Redis.get(key)
              ├─ HIT  ──► 回答（快）
              └─ MISS ──► Agent ──► Redis.set ──► 回答
```

| 组件 | 存什么 | 挂了会怎样 |
|------|--------|------------|
| Redis | key → 最终回答 | 全部走 miss，系统仍能答，只是变慢 |
| Ollama | （模型进程） | miss 时无法生成；hit 仍可返回旧缓存 |
| Agent 代码 | 无持久状态 | 逻辑本身；缓存只是外包一层 |

---

## 环境准备

- Python 3.12+、[uv](https://github.com/astral-sh/uv)、Docker Desktop  
- 本机 [Ollama](https://ollama.com/) 已拉取模型（默认示例用 `qwen2:7b`，可用环境变量改）  
- 若本机 **6379** 已被其它 Redis 占用，本文把服务映射到 **6389**

在空目录创建文件（下文给出完整内容）。

`docker-compose.yml`：

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6389:6379"
    command: ["redis-server", "--save", "", "--appendonly", "no"]
```

`pyproject.toml`：

```toml
[project]
name = "day23-redis-cache"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "redis>=5.0.0",
  "langchain>=1.0",
  "langchain-ollama>=0.3",
  "langgraph>=0.2",
]
```

`redis_config.py`：

```python
REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6389
```

启动：

```bash
docker compose up -d
docker compose ps    # redis 应为 Up
uv sync
```

---

## 步骤 1：连通 Redis，看清 MISS / HIT

`step01_redis_ping.py`：

```python
"""连通 Redis，演示 SET / GET / TTL / 命中。"""

from __future__ import annotations

import time

import redis

from redis_config import REDIS_HOST, REDIS_PORT

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

print(f"连 {REDIS_HOST}:{REDIS_PORT}")
print("PING ->", r.ping())

key = "day23:demo:llm:what-is-redis"
value = "Redis 是内存里的键值缓存，常用来记住 LLM 的完整回答。"

cached = r.get(key)
if cached is None:
    print("MISS：缓存没有，假装调用 LLM…")
    time.sleep(0.5)
    r.set(key, value, ex=60)
    print("已写入 Redis，TTL=60s")
else:
    print("HIT：直接读缓存，不调 LLM")
    print("  value =", cached)

print("再 GET ->", r.get(key))
print("剩余 TTL(秒) ->", r.ttl(key))
```

```bash
uv run python step01_redis_ping.py
uv run python step01_redis_ping.py
```

**期望**：第一次 `MISS`（有 0.5s sleep）；第二次 `HIT`（不再 sleep）；`TTL` 从约 60 递减。

---

## 步骤 2：给 Agent 缓存最终 LLM 响应

核心逻辑只有三步：`cache_key` → `get` → 没有则 `run_agent` 再 `set`。

`step02_agent_llm_cache.py`：

```python
"""最小 Agent + Redis 缓存最终回答。"""

from __future__ import annotations

import hashlib
import os
import time

import redis
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage

from redis_config import REDIS_HOST, REDIS_PORT

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))
QUESTION = os.getenv(
    "QUESTION",
    "单词 agent 有几个字母？把结果加10",
)

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def cache_key(question: str) -> str:
    digest = hashlib.sha256(question.strip().encode("utf-8")).hexdigest()[:16]
    return f"day23:llm:{digest}"


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def build_agent():
    return create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[get_word_length, add],
        system_prompt=(
            "你是严谨的助手。需要长度或加法时必须调用工具，禁止心算。"
            "先 get_word_length，再用返回的整数调用 add。"
        ),
    )


def run_agent(question: str) -> str:
    agent = build_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    for msg in reversed(result["messages"]):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return "(no final answer)"


def ask_with_cache(question: str) -> tuple[str, str, float]:
    key = cache_key(question)
    t0 = time.perf_counter()
    cached = r.get(key)
    if cached is not None:
        return cached, "hit", time.perf_counter() - t0

    answer = run_agent(question)
    r.set(key, answer, ex=CACHE_TTL)
    return answer, "miss", time.perf_counter() - t0


def main() -> None:
    print(f"Redis {REDIS_HOST}:{REDIS_PORT}  PING={r.ping()}")
    print(f"问句: {QUESTION}")
    print(f"key : {cache_key(QUESTION)}")
    answer, status, elapsed = ask_with_cache(QUESTION)
    print(f"[{status}] {elapsed:.2f}s")
    print(f"回答: {answer[:200]}")


if __name__ == "__main__":
    main()
```

```bash
uv run python step02_agent_llm_cache.py
uv run python step02_agent_llm_cache.py
```

**期望示例**（秒数因机器而异）：

```text
[miss] 33.14s
回答: 结果是 15。
…
[hit] 0.00s
回答: 结果是 15。
```

两次 key 相同；hit 时**不会**再跑工具与 Ollama。

---

## 步骤 3：同问句对比优化前后

`step03_compare_latency.py` 会先 `DEL` 该 key，再连跑两次，保证第一次一定是 miss：

```python
"""同问句连跑两次，打印前后延迟对比。"""

from __future__ import annotations

from step02_agent_llm_cache import QUESTION, ask_with_cache, cache_key, r

key = cache_key(QUESTION)
print(f"PING={r.ping()}  key={key}")
print(f"问句: {QUESTION}")
deleted = r.delete(key)
print(f"已清空该 key（删 {deleted} 条），开始对比\n")

rows = []
for i in range(1, 3):
    answer, status, elapsed = ask_with_cache(QUESTION)
    rows.append((i, status, elapsed, answer[:80]))
    print(f"第{i}次  [{status}]  {elapsed:.3f}s  |  {answer[:80]}")

miss_t = next(t for _, s, t, _ in rows if s == "miss")
hit_t = next(t for _, s, t, _ in rows if s == "hit")

print("\n--- 对比（同问句：无缓存 vs 有缓存）---")
print(f"无缓存(miss) ≈ {miss_t:.2f}s")
print(f"有缓存(hit)  ≈ {hit_t:.3f}s")
if hit_t > 0:
    print(f"加速约 {miss_t / hit_t:.0f}x")
else:
    print("hit 亚毫秒级；相对 miss 相当于跳过整次 LLM")
```

```bash
uv run python step03_compare_latency.py
```

---

## 新手向坑

### 1. `Connection refused` / Docker sock 找不到

**现象**：连不上 `127.0.0.1:6379` 或 `6389`。  
**原因**：Docker Desktop 未启动，或 Compose 未 `up`。  
**处理**：先开 Docker，再 `docker compose up -d`，确认 `ps` 为 Up。

### 2. `Bind for 0.0.0.0:6379 failed: port is already allocated`

**现象**：Compose 起失败，但有时脚本仍能连上。  
**原因**：本机 6379 已被其它容器/进程占用。  
**处理**：本文映射 **6389→6379**；客户端端口与 `redis_config.py` 保持一致，避免串到别的项目的 Redis。

### 3. 两次都是 hit，对比不出加速

**原因**：key 还在。  
**处理**：用步骤 3（先 `DEL`），或换一句问句 / 等 TTL 过期。

### 4. 改大小写却期望命中

**原因**：key 来自问句哈希，**精确匹配**。  
**处理**：需要「语义相同也命中」要另做规范化或语义缓存，不在本文范围。

---

## 边界：做了什么 / 故意没做什么

**做了**：Redis 基础；Agent 最终响应缓存；同问句延迟对比；TTL 与 key 设计。

**没做**：LiteLLM 云端缓存全套配置；异步接口改造；Embedding 缓存完整工程化；vLLM；locust / jmeter 压测；把 FastAPI + Milvus + Redis 打成一键 Compose（后续周次再串）。

生产上还可继续：按用户隔离 key、缓存旁路、失效策略、只缓存确定性任务等——本文先把「缓存 LLM 响应」这条主链路跑通。

---

## 小结

| 步骤 | 动作 |
|------|------|
| 基础 | Redis = 内存键值缓存；HIT 跳过重算 |
| 挂 Agent | `get` → miss 则 `run_agent` → `set` 最终回答 |
| 对比 | 同问句 miss 数十秒 vs hit ~0s |
| 选型 | 响应缓存砍「等模型」；检索缓存只省找资料 |

先量清瓶颈，再对「相同问句」记住答案——往往是性价比最高的一刀。
