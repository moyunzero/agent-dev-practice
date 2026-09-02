# 给 Agent 加对话记忆：从 ConversationBufferMemory 到 checkpointer

多轮聊天里，用户先说「我叫墨墨」，再问「我叫什么？」——若每轮只把**当前这一句**发给模型，第二问常常答不上来。  
上游 Day19 目标：**为 Agent 添加对话历史记忆（ConversationBufferMemory）**。本文先演示「无记忆」的失败，再用现版 LangChain `create_agent` + **`InMemorySaver` checkpointer** + 同一 **`thread_id`** 实现等价的「对话缓冲」效果；并说明 Mem0 等长期记忆产品与短期缓冲的差别。

## 你将会得到什么

1. 说清为什么默认 LLM 调用「不记得」上一轮  
2. 理解 ConversationBufferMemory：把历史消息带进后续请求  
3. 用 `InMemorySaver` + `thread_id` 跑通「同会话记得 / 换会话忘掉」  
4. 分清：进程内短期缓冲 vs Mem0 类跨会话长期记忆  

---

## 零基础名词表

> 建议先读完再动手。

### 为什么模型会「忘」

| 层 | 说明 |
|----|------|
| **是什么** | 单次 API 调用通常只看到**你这次请求里放进的 messages** |
| **在本文干什么** | 无记忆时，第二轮只发「我叫什么名字？」→ 请求里没有「墨墨」 |
| **怎么区分** | 不是模型硬盘坏了，是**你没把历史带过去** |

### ConversationBufferMemory（对话缓冲记忆）

| 层 | 说明 |
|----|------|
| **是什么** | LangChain 经典 Memory：把对话消息**原样缓冲**，拼进后续 Prompt / 消息列表 |
| **在本文干什么** | 上游点名要实现的能力：同一会话内，后一轮能用上前一轮内容 |
| **怎么区分** | 「Buffer」= 缓冲聊天记录；还有摘要记忆、实体记忆等变体，本日只做缓冲 |

### checkpointer 与 `thread_id`（现版落地）

| 层 | 说明 |
|----|------|
| **是什么** | LangGraph / `create_agent` 用 checkpointer **存取会话状态**；`thread_id` 标识哪一条会话 |
| **在本文干什么** | `InMemorySaver` 存内存；同一 `thread_id` 多轮自动带历史；换 id = 新聊天室 |
| **怎么区分** | 与旧 `ConversationBufferMemory` **目标相同**（历史进上下文），**API 不同**。学能力时两者等价理解即可 |

```text
同 thread_id：
  轮1「我叫墨墨」→ 存进 checkpointer
  轮2「我叫什么？」→ 自动带上轮1 → 答「墨墨」

换 thread_id：
  轮3「我叫什么？」→ 空历史 → 答不上
```

### `InMemorySaver`

| 层 | 说明 |
|----|------|
| **是什么** | 把 checkpoint 存在**当前进程内存**里 |
| **在本文干什么** | 本地 demo 零配置 |
| **怎么区分** | **进程结束就清空**。不是写进数据库的永久记忆。需要持久化要用 SQLite/Postgres 等 checkpointer（本日不展开） |

### 短期记忆 vs 长期记忆（Mem0 / MemoryScope）

| 层 | 说明 |
|----|------|
| **是什么** | 短期：本次会话缓冲。长期：跨天、跨会话的用户偏好 / 事实，常落库 |
| **在本文干什么** | 上游资源提到 Mem0、MemoryScope——知悉其定位 |
| **怎么区分** | 今天做的 Buffer / InMemory = 短期。Mem0 ≠ 换个名字的 BufferMemory |

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) + 模型（如 `qwen2:7b`）  

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day19-agent-memory && cd day19-agent-memory
```

### `pyproject.toml`

```toml
[project]
name = "day19-agent-memory"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langchain>=1.3.16",
    "langchain-ollama>=1.1.0",
    "langgraph>=0.4.0",
]
```

```bash
uv sync
```

### 对照 A：无记忆

```python
from langchain.agents import create_agent

agent = create_agent(model="ollama:qwen2:7b", tools=[], system_prompt="简洁回答。")

# 两轮各自 invoke，第二轮 messages 里只有当前问句 → 常忘名字
agent.invoke({"messages": [{"role": "user", "content": "我叫墨墨。请记住。"}]})
agent.invoke({"messages": [{"role": "user", "content": "我叫什么名字？"}]})
```

### 对照 B：有缓冲记忆

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

agent = create_agent(
    model="ollama:qwen2:7b",
    tools=[],
    checkpointer=InMemorySaver(),
    system_prompt="记住用户个人信息，简洁回答。",
)
cfg = {"configurable": {"thread_id": "chat-1"}}

agent.invoke(
    {"messages": [{"role": "user", "content": "你好，我叫墨墨。请记住我的名字。"}]},
    config=cfg,
)
r = agent.invoke(
    {"messages": [{"role": "user", "content": "我叫什么名字？"}]},
    config=cfg,
)
print(r["messages"][-1].content)  # 期望提到「墨墨」

# 换 thread → 新会话
agent.invoke(
    {"messages": [{"role": "user", "content": "我叫什么名字？"}]},
    config={"configurable": {"thread_id": "chat-other"}},
)
```

```bash
uv run python demo_memory_agent.py
```

**期望**：同 `thread_id` 答出名字；换 `thread_id` 答不出该名。

---

## 新手坑

### 1. 加了 checkpointer 却每轮换新 `thread_id`

| | |
|--|--|
| **现象** | 仍然忘记 |
| **原因** | 每个 id 是独立会话 |
| **处理** | 同一用户会话固定同一个 `thread_id` |

### 2. 以为 InMemory 重启后还在

| | |
|--|--|
| **现象** | 重跑脚本，旧对话没了 |
| **原因** | 内存缓冲，进程结束即清空 |
| **处理** | 要持久化再选落盘 checkpointer / 长期记忆方案 |

### 3. 把 Mem0 当成今天必装依赖

| | |
|--|--|
| **说明** | 上游目标是对话历史缓冲；Mem0 是另一层能力，本日不必实装 |

---

## 本文边界

**做了什么**：无记忆对照；InMemorySaver + thread_id；与 ConversationBufferMemory 概念对齐。  

**故意没展开**：Mem0 / MemoryScope 实战、摘要裁剪、Redis/SQLite checkpointer。

---

## 延伸阅读

- [LangChain Agents · Conversation History](https://docs.langchain.com/oss/python/langchain/agents)  
- [Short-term memory](https://docs.langchain.com/oss/python/langchain/short-term-memory)  
- [Mem0](https://github.com/mem0ai/mem0)（长期记忆，选读）  

---

## 收束

1. **忘了** = 请求里没带历史，不是玄学。  
2. **BufferMemory** ≈ 缓冲消息；现版用 **checkpointer + 同一 thread_id**。  
3. **InMemory** 随进程结束消失；跨会话长期记忆看 Mem0 一类，另开一层。
