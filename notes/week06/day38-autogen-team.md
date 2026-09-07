# 用 AutoGen AgentChat 搭「研究员–程序员–测试员」三人协作小队

学习路线里常要求：用 AutoGen 做一个 **「研究员–程序员–测试员」** 的 Multi-Agent 系统。  
概念上这是三人软件小队；代码上请用 **现役 AgentChat**（`AssistantAgent` + `RoundRobinGroupChat`），不要照抄 v0.2 的 `ConversableAgent` / 旧 `GroupChat`。

本文对齐官方 [Teams](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html)、[Agents](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html)、[Termination](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html)，用本机 **Ollama** 跑通最小三人轮转示例。

> AutoGen 已进入 maintenance mode；新绿项目可关注 [Microsoft Agent Framework](https://github.com/microsoft/agent-framework)。若路线仍要求 AutoGen，学 **当前 AgentChat API** 即可。

## 你将会得到什么

1. 说清三人角色各自职责，以及为何拆成三个 Agent  
2. 用同一套 RoundRobin 会议室，把两人协作扩成三人  
3. 理解群聊「共享状态」= 消息历史  
4. 用 `TextMentionTermination` + `MaxMessageTermination` 控制何时散会  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### Multi-Agent（多智能体）

| 层 | 说明 |
|----|------|
| **是什么** | 多个带不同职责的 Agent 一起完成一件事，而不是一个全能助手包办 |
| **在本文干什么** | 研究员拆需求、程序员写代码、测试员验收 |
| **怎么区分** | 不是「同时开三个 ChatGPT 网页」；是**同一段程序**里编排谁先谁后 |

### 角色（Role）与 `system_message`

| 层 | 说明 |
|----|------|
| **是什么** | 给助手定的工牌规矩：该说什么、不该说什么 |
| **在本文干什么** | 写在每个 `AssistantAgent` 的 `system_message` 里 |
| **怎么区分** | 角色是设定；真正「想出内容」的仍是 Ollama 上的模型 |

### RoundRobinGroupChat（轮转群聊）

| 层 | 说明 |
|----|------|
| **是什么** | 按名单固定顺序轮流发言的「会议室」规则 |
| **在本文干什么** | `researcher → coder → tester → …` |
| **怎么区分** | `SelectorGroupChat` 是「每次选合适的人」；本文只用 RoundRobin |

### 共享状态（对话上下文）

| 层 | 说明 |
|----|------|
| **是什么** | 多人协作时，后发言者能看见的「到目前为止说了什么」 |
| **在本文干什么** | 就是群聊的**消息历史**；研究员的要点，程序员和测试员都能看到 |
| **怎么区分** | 本文没有另建 Redis/数据库；状态主要挂在对话里 |

### 终止条件（Termination）

| 层 | 说明 |
|----|------|
| **是什么** | 规定什么时候散会，避免永远聊下去 |
| **在本文干什么** | 出现 `APPROVE` **或** 消息条数触顶就停 |
| **怎么区分** | `TextMentionTermination` 看关键词；`MaxMessageTermination` 看条数；`A \| B` 表示任一满足即停 |

### Ollama 与接线员

| 层 | 说明 |
|----|------|
| **是什么** | Ollama 在本机提供大模型；`OllamaChatCompletionClient` 负责连上它 |
| **在本文干什么** | 三个助手共用一个接线员 |
| **怎么区分** | 客户端是接线员；模型是脑子 |

---

## 三人职责一张表

| 角色 | Agent 名 | 干什么 | 不干什么 |
|------|----------|--------|----------|
| 研究员 | `researcher` | 拆成目标 / 输入 / 输出 / 约束 | 不写长代码 |
| 程序员 | `coder` | 按要点写短实现 | 不自己盖章通过 |
| 测试员 | `tester` | 列短用例；够好就说 `APPROVE` | 不重写整份需求 |

为什么拆三个：一个人又调研又写又测，职责容易糊在一起；拆开后对话里能看清谁负责哪一步。

```text
用户任务
   │
   ▼
┌──────────────────────────────────────┐
│  RoundRobinGroupChat                 │
│  [researcher, coder, tester]         │
│  共享状态 = 消息历史                   │
└──────────────────────────────────────┘
   │
   ▼
出现 APPROVE  或  消息条数到上限  → 散会
```

---

## 环境准备

- Python 3.10+、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) 已启动，并已 `pull` 模型（下文默认 `llama3.1:8b`）  

```toml
# pyproject.toml
[project]
name = "day38-autogen-team"
version = "0.1.0"
description = "Day38: AutoGen AgentChat researcher-coder-tester Multi-Agent team"
requires-python = ">=3.10"
dependencies = [
  "autogen-agentchat==0.7.5",
  "autogen-ext[ollama]==0.7.5",
]
```

```bash
uv sync
# 可选：export OLLAMA_MODEL=你的模型名
```

确认 Ollama：

```bash
curl -s http://127.0.0.1:11434/api/tags | head
```

---

## 完整示例：三人开发小队

把下面保存为 `step02_dev_team.py`（或任意文件名）：

```python
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

    researcher = AssistantAgent(
        name="researcher",
        model_client=model_client,
        system_message=(
            "你是研究员。把用户需求拆成极短的要点："
            "目标、输入、输出、约束。用中文条目列出，不要写代码。"
        ),
    )
    coder = AssistantAgent(
        name="coder",
        model_client=model_client,
        system_message=(
            "你是程序员。根据研究员的要点，用 Python 写一个很短的函数实现。"
            "只输出代码，不要长篇解释。"
        ),
    )
    tester = AssistantAgent(
        name="tester",
        model_client=model_client,
        system_message=(
            "你是测试员。根据程序员的代码，列出 2～3 条简短测试用例（中文）。"
            "若实现清楚且可测，只回复：APPROVE。"
            "否则只指出一个问题，不要重写全部代码。"
        ),
    )

    termination = TextMentionTermination("APPROVE") | MaxMessageTermination(9)

    team = RoundRobinGroupChat(
        [researcher, coder, tester],
        termination_condition=termination,
    )

    print("=== 三人小队开始协作（看到 researcher / coder / tester 交替即可）===\n")
    await Console(
        team.run_stream(
            task=(
                "写一个 Python 函数 celsius_to_fahrenheit(c: float) -> float，"
                "把摄氏度转成华氏度。要求：短小、可测。"
            )
        )
    )

    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### 关键 API（对照官方）

| API | 常用入参 | 出参 / 行为 | 何时用 |
|-----|----------|-------------|--------|
| `AssistantAgent` | `name`、`model_client`、`system_message` | Agent 实例 | 需要有角色的说话者 |
| `RoundRobinGroupChat` | 参与者列表、`termination_condition` | Team；`run_stream(task=...)` | 固定顺序协作 |
| `TextMentionTermination` | 关键词字符串 | 命中则停 | 测试员说 `APPROVE` |
| `MaxMessageTermination` | `max_messages` | 条数触顶则停 | 防本地小模型聊不停 |
| `Console` | 传入 `run_stream` 异步流 | 打印到终端 | 想看清谁在说话 |

### 运行与期望

```bash
uv run python step02_dev_team.py
```

**期望**：终端交替出现 `researcher` / `coder` / `tester`；因 `APPROVE` 或消息上限结束。  
本地小模型不一定立刻 `APPROVE`，也不保证三人内容完全一致——这正是条数上限存在的原因。

---

## 新手向坑

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 连不上模型 | Ollama 未启动 / 模型名不对 | `ollama serve`；核对 `OLLAMA_MODEL` 与 `ollama list` |
| 研究员也写了一大段代码 | 小模型不严格遵守 system_message | 把任务写得更短；或接受「演示协作结构」优先于完美角色纪律 |
| 程序员方向写反、测试员没 APPROVE | 角色之间未真正对齐 | 正常；可把 `MaxMessageTermination` 调大一点再观察，或收紧提示词 |
| 条数一改小立刻结束 | `MaxMessageTermination` 生效 | 例如改成 `4` 会更早强制散会（含用户任务消息） |

---

## 边界：做了什么 / 故意没做什么

**做了**：三人角色定义、RoundRobin 协作、消息历史作为共享状态、双终止条件、本机 Ollama 可跑示例。  

**没做**：真的执行代码 / 跑 pytest、挂文件工具、`SelectorGroupChat`、层级式经理分派、CrewAI（通常在后续路线）。

---

## 小结

把「研究员–程序员–测试员」落成代码，核心不是新框架花活，而是：

1. 三个 `AssistantAgent` + 清晰 `system_message`  
2. 同一个 `RoundRobinGroupChat` 按名单轮流  
3. 用终止条件收场  

会议室骨架与两人轮转相同；变的是**角色设计与名单长度**。

*系列笔记 · Agent 工程跟练 · Week 6 Day 38*
