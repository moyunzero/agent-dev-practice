# 用现役 AutoGen AgentChat 跑通「可对话 Agent」与轮转群聊

路线表里常写 `ConversableAgent`、`GroupChat`——那是 **AutoGen v0.2** 时代的名字。  
今天要学的**概念**没变（雇会说话的助手、多人轮流协作），但**代码必须跟当前 stable AgentChat**，否则安装与 import 会对不上。

本文对齐官方 [AgentChat 文档](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/)、[Quickstart](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/quickstart.html)、[Migration Guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html)，用本机 **Ollama** 跑两个最小例子：

1. 单个 `AssistantAgent` + `run`  
2. 两个助手 + `RoundRobinGroupChat` + `run_stream` / `Console`  

> 官方 README 标明 AutoGen 已进入 **maintenance mode**，新绿项目可关注 [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)。若你的学习路线仍要求 AutoGen，请学 **当前 AgentChat API**，不要照抄 v0.2 教程。

## 你将会得到什么

1. 说清上游旧名与现役 API 的映射，以及为何不能 `from autogen import ConversableAgent`  
2. 分清 `autogen-agentchat` / `autogen-ext`（以及中间的 core）各自干什么  
3. 跑通单助手与「写手–评审」轮转群聊  
4. 对照官方含义，知道 `run` vs `run_stream`、两种终止条件何时用  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### Agent（助手）

| 层 | 说明 |
|----|------|
| **是什么** | 程序里带角色设定、会调用大模型说话的对象 |
| **在本文干什么** | `AssistantAgent`：单个或群聊里的参与者 |
| **怎么区分** | 不是 ChatGPT 网页本身；是你代码里的一个变量 |

### 大模型与 Ollama

| 层 | 说明 |
|----|------|
| **是什么** | 大模型根据文字生成文字；Ollama 在本机提供模型服务 |
| **在本文干什么** | 真正「想出回答」的是 Ollama 上的模型（如 `llama3.1:8b`） |
| **怎么区分** | `OllamaChatCompletionClient` 是**接线员**；模型才是**脑子** |

### AutoGen AgentChat（现役）

| 层 | 说明 |
|----|------|
| **是什么** | 微软 AutoGen 里偏「任务向、好上手」的一层 API |
| **在本文干什么** | `AssistantAgent`、`RoundRobinGroupChat`、`Console` |
| **怎么区分** | v0.2 的 `ConversableAgent`/`GroupChat` 是旧皮；概念可对齐，代码不能照抄 |

### 三层包

```text
autogen-agentchat  ← 助手、群聊、终止条件、Console
        │
autogen-core       ← 消息与运行时（多数时候先不用直接摸）
        │
autogen-ext        ← 模型客户端等扩展（本文用 Ollama）
```

### RoundRobin vs Selector

| | 谁下一个说话 |
|--|--------------|
| **RoundRobinGroupChat** | 按名单固定顺序轮流 |
| **SelectorGroupChat** | 模型/规则挑选合适的人 |

本文只练 RoundRobin。

### `run` vs `run_stream`

| | 行为（官方 Agent 共性） |
|--|-------------------------|
| **`run`** | 给定 task，返回完整 **`TaskResult`** |
| **`run_stream`** | 同样干活，但边跑边产出消息流；最后一项仍是结果 |

单助手示例用 `run`；群聊示例用 `run_stream` + `Console` 方便看见谁在说话。

---

## 上游旧名 → 现役映射

| 上游 / v0.2 | 现役 | 一句话 |
|-------------|------|--------|
| `ConversableAgent` | `AssistantAgent` | 常用 LLM 对话助手 |
| `GroupChat` + Manager | `RoundRobinGroupChat`（或 `SelectorGroupChat`） | 多人协作会议室规则 |
| `llm_config=...` | `OllamaChatCompletionClient` / `OpenAIChatCompletionClient` | 模型客户端 |
| 同步 `initiate_chat` | `async` `run` / `run_stream` | 现役以 asyncio 为主 |

口诀：**概念对齐上游，代码对齐 stable。**

---

## 环境准备

- Python 3.10+、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) 已启动，并已 `pull` 模型（下文默认 `llama3.1:8b`）  

```toml
# pyproject.toml
[project]
name = "day36-37-autogen-core"
version = "0.1.0"
description = "AutoGen AgentChat core concepts (current stable API)"
requires-python = ">=3.10"
dependencies = [
  "autogen-agentchat==0.7.5",
  "autogen-ext[ollama]==0.7.5",
]
```

```bash
uv sync
curl -s http://127.0.0.1:11434/api/tags | head
```

官方安装说明亦见：[Installation](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/installation.html)（示例常写 `pip install -U "autogen-agentchat" "autogen-ext[openai]"`；本文用 `[ollama]` 接本地模型）。

---

## 本课关键 API（入参 / 出参 / 何时用）

依据官方参考与 0.7.5 签名摘要如下（完整表可对照练习目录讲义）。

### `OllamaChatCompletionClient`

- **入参**：`model`（必填）；`host`、`model_info` 等可选（文档：不在预置列表的模型可能需要 `model_info`）  
- **作用**：连 Ollama  
- **收尾**：`await model_client.close()`（Quickstart 亦如此）  
- 文档：[autogen_ext.models.ollama](https://microsoft.github.io/autogen/stable/reference/python/autogen_ext.models.ollama.html)

### `AssistantAgent`

- **入参（常用）**：`name`、`model_client` 必填；`system_message`、`tools` 等可选  
- **何时用**：需要一个会调用模型说话的角色  
- 文档：[Agents](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.agents.html)

### `await agent.run(task=...)`

- **入参 `task`**：`str` / 消息 / 消息序列 / `None`  
- **出参**：`TaskResult`（字段含 `messages`、`stop_reason`）  
- **何时用**：单助手、一次拿齐结果  

### `RoundRobinGroupChat`

- **入参**：`participants` 列表；可选 `termination_condition`、`max_turns` 等  
- **何时用**：固定顺序轮流发言  
- 文档 / 示例：[Migration Guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html)

### 终止条件

| API | 入参要点 | 何时用 |
|-----|----------|--------|
| `TextMentionTermination(text, sources=None)` | 出现某段文字就停；可限特定说话者 | 口令结束（如 `APPROVE`） |
| `MaxMessageTermination(max_messages, ...)` | 消息条数上限 | 防止无限聊 |

可用 `|` 组合：**任一满足即停**（官方 Migration 示例同款写法）。

### `Console(stream)`

- **入参**：来自 `run_stream` 的异步流  
- **返回**：最后的 `TaskResult`（对流来自 `run_stream` 时）  
- **何时用**：把多人对话一条条打到终端  
- 文档：[UI Console](https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.ui.html)

---

## 示例 1：单个 AssistantAgent

```python
"""单助手：对齐官方 Quickstart 风格，模型改为 Ollama。"""

from __future__ import annotations

import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.ollama import OllamaChatCompletionClient

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


async def main() -> None:
    model_client = OllamaChatCompletionClient(model=MODEL)
    agent = AssistantAgent(
        "assistant",
        model_client=model_client,
        system_message="你是简洁助手。回答尽量短。",
    )

    result = await agent.run(task="用一句话介绍你自己。只输出一句中文。")
    print(result)
    if result.messages:
        print(getattr(result.messages[-1], "content", result.messages[-1]))

    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

```bash
uv run python step02_assistant_hello.py
```

**期望**：终端出现 `TaskResult`，最后有一句中文自我介绍。

---

## 示例 2：RoundRobin 写手 + 评审

```python
"""两个助手轮流说话：RoundRobinGroupChat。"""

from __future__ import annotations

import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.ollama import OllamaChatCompletionClient

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")


async def main() -> None:
    model_client = OllamaChatCompletionClient(model=MODEL)

    writer = AssistantAgent(
        name="writer",
        model_client=model_client,
        system_message=(
            "你是写手。根据任务写一句很短的中文产品口号。"
            "每次只输出一句口号，不要解释。"
        ),
    )
    critic = AssistantAgent(
        name="critic",
        model_client=model_client,
        system_message=(
            "你是评审。若口号清楚好记，只回复：APPROVE。"
            "否则只回复一句简短修改建议（中文）。不要长篇大论。"
        ),
    )

    termination = TextMentionTermination("APPROVE") | MaxMessageTermination(6)
    team = RoundRobinGroupChat([writer, critic], termination_condition=termination)

    await Console(
        team.run_stream(task="为「本地笔记 App」写一句中文口号。要短、好记。")
    )
    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

```bash
uv run python step03_roundrobin_two_agents.py
```

**期望**：终端交替出现 `writer` / `critic`；因 `APPROVE` 或达到消息上限而结束。本地小模型不一定立刻 APPROVE——这正是 `MaxMessageTermination` 存在的原因。

---

## 新手向坑

| 现象 | 原因 | 处理 |
|------|------|------|
| `from autogen import ConversableAgent` 失败 | 在用 v0.2 写法 | 改用 `autogen_agentchat` / `autogen_ext` |
| 连不上模型 | Ollama 未起或未 pull | `ollama serve`；`ollama pull llama3.1:8b` |
| 群聊聊不停 | 未设终止条件 | `TextMentionTermination` 与/或 `MaxMessageTermination` |
| 把 Client 当成「脑子」 | 概念混淆 | Client = 接线员；模型 = 脑子 |

---

## 边界

| 做了 | 没做 |
|------|------|
| 现役 AgentChat 单助手 + RoundRobin | v0.2 API、完整 Selector 深挖 |
| Ollama 本地推理 | 强制 OpenAI Key |
| 对照官方讲清常用 API | Day38 三人角色大作业、CrewAI |

下一步路线常见是 AutoGen 实战（多人角色团队）或转入 CrewAI——以你的学习路线表为准。

---

## 小结

1. **ConversableAgent → AssistantAgent**；**GroupChat → RoundRobinGroupChat**（本篇）  
2. **agentchat** 编排助手与群聊；**ext** 接 Ollama 等客户端  
3. 单助手用 **`run`**；多人轮流用 **`RoundRobinGroupChat` + `run_stream`/`Console`**，并用终止条件收束  

*系列笔记 · Agent 工程跟练 · Week 6 Day 36–37*
