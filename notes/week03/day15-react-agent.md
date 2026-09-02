# 理解 ReAct：用 LangChain create_agent 跑通第一个带工具的 Agent

只会「检索文档 → 拼 Prompt → 模型答一次」的 RAG，遇到「先查长度再做加减」这类题会很别扭：答案往往不在文档里，而在**计算或外部 API**里。  
**Agent** 换了一种做法：让大模型在循环里自己决定「要不要调工具、调哪个、看到结果后再干什么」。这篇用本地 Ollama + LangChain 官方入口 `create_agent`，把 **ReAct（Reasoning + Acting）** 跑通，并看清 Thought / Action / Observation。

## 你将会得到什么

1. 说清固定 RAG 链和 ReAct Agent 差在「谁决定下一步」  
2. 认识 docstring、`@tool`、schema（工具名片）分别干什么  
3. 从空目录用 `create_agent` + 两个小工具跑出可打印的 ReAct 轨迹  
4. 避开三个新手坑：忘了 `@tool`、没登记进 `tools=`、system_prompt 把模型带歪  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按「是什么 → 在本文干什么 → 怎么区分」展开。

### RAG（检索增强生成） vs Agent

```text
固定 RAG 链（代码写死步骤）
  问句 → [检索文档] → [拼 Prompt] → [LLM 生成一次] → 答案

ReAct Agent（模型决定下一步）
  问句 → Thought → Action(调工具) → Observation(工具结果)
       → Thought → … → 最终答案
```

| 层 | 说明 |
|----|------|
| **是什么** | RAG：先从知识库找相关段落，再让模型依据段落回答。Agent：模型可多步行动，常配合**工具**完成查天气、算数、查库等 |
| **在本文干什么** | 用「字母数再加 10」对比：RAG 需要事先写好的文档；Agent 用工具算出来 |
| **怎么区分** | RAG 的下一步在**程序员写的流水线**里；Agent 的下一步多半由**模型**根据 Observation 决定 |

两者可以组合（例如「研究助手」又检索又搜索），但入门时先分清：**有没有「模型自己选工具」这一环**。

### ReAct

| 层 | 说明 |
|----|------|
| **是什么** | Reasoning + Acting：边想边做。经典写法里循环出现三类标记：**Thought**（思考）、**Action**（行动）、**Observation**（观察结果） |
| **在本文干什么** | 用打印消息的方式，把 LangChain Agent 跑出来的轨迹「翻译」回这三类标记，方便对照论文/博客 |
| **怎么区分** | 不是一种单独的 Python 库名；是一种**工作流想法**。现代框架常用「工具调用（tool call）」实现 Action，不一定在文本里打印出 `Thought:` 字样 |

人话类比：你查「北京比上海高几度」——先想要气温（Thought）→ 查北京（Action）→ 看到 28°C（Observation）→ 再查上海 → 最后相减回答。

### Thought / Action / Observation

| 标记 | 谁产生 | 干什么 |
|------|--------|--------|
| **Thought** | 大模型（推理） | 决定「还缺什么信息、下一步干什么」 |
| **Action** | 大模型发起；框架去执行 | 调用某个工具，并带上参数，例如 `add(a=5, b=10)` |
| **Observation** | **工具函数的返回值** | 把真实结果喂回模型，例如 `15` |

在 LangChain / LangGraph 消息里，常见对应是：

- **Action** ≈ `AIMessage` 里带有的 `tool_calls`  
- **Observation** ≈ `ToolMessage` 的内容  
- **Thought** 有时写在模型文本里；很多「原生 tool calling」场景里，思考被折叠进「决定调哪个工具」，打印轨迹时我们用「模型决定调用 xxx」来表示这一步  

### 工具（Tool）

| 层 | 说明 |
|----|------|
| **是什么** | 带名字、说明、参数约定的**可调用函数**。模型不能真的「伸手」碰天气 API 或计算器，只能通过框架去调你注册好的工具 |
| **在本文干什么** | `get_word_length` 算字母数；`add` 做加法。问题需要两步时，模型会链式调用 |
| **怎么区分** | 普通 Python 函数只有代码能直接 `add(5,10)`；**工具**还要让模型「看见说明书」并被框架调度 |

### docstring（文档字符串）

| 层 | 说明 |
|----|------|
| **是什么** | 写在函数（或类、模块）**开头**、用三引号 `"""..."""` 包起来的说明文字。Python 会把它挂在函数的 `__doc__` 上 |
| **在本文干什么** | `@tool` 会把 docstring 收成工具名片上的 **description**，交给大模型读：「这个工具是干什么的」 |
| **怎么区分** | `# 注释` 只给人扫一眼，程序通常不当正式文档用；**docstring** 可被程序读到。空 docstring 时模型仍可能靠函数名瞎猜，更容易选错工具 |

### schema（工具名片）与 `@tool`

| 层 | 说明 |
|----|------|
| **是什么** | schema 这里指：工具名 + 说明 + 参数名/类型/是否必填。像一张给模型看的点菜单 |
| **在本文干什么** | `@tool` 装饰器把「普通函数 + docstring + 类型注解（如 `a: int`）」自动变成 schema，不必手写一大段 JSON |
| **怎么区分** | 你写的是 Python；模型看到的是结构化说明书。漏了 `@tool`，或没放进 `create_agent(..., tools=[...])`，模型就**看不到**这个工具 |

名片上通常三样信息：

1. 工具名（函数名）  
2. 说明（多半来自 docstring）  
3. 参数（名字、类型、必填与否）

### `create_agent`（LangChain 官方 Agent 入口）

| 层 | 说明 |
|----|------|
| **是什么** | 当前 LangChain 推荐的创建 Agent 方式；底层用 LangGraph 状态机跑「模型 ↔ 工具」循环 |
| **在本文干什么** | 传入 `model`、`tools`、可选 `system_prompt`，一次 `invoke` 得到完整消息列表 |
| **怎么区分** | Week1 的 **LCEL**（`prompt \| model \| parser`）是**固定管道**，走一次就结束。`create_agent` 可能**多轮**调工具，直到模型给出最终文本答案 |

**导入与版本**：本文按 `pyproject.toml` 锁定 **LangChain ≥ 1.3**，使用：

```python
from langchain.agents import create_agent
```

若你用的是更旧的栈（大致 LangChain 0.3 之前 / 早期 LangGraph 教程），网上示例可能是 `langgraph.prebuilt.create_react_agent`——那是另一条入口，API 不完全相同。**跟本文复现时请按依赖锁定版本**，不要混用旧教程的 import。

旧文档里还常见 `AgentExecutor` + 手写 ReAct 提示词；新代码优先学 `create_agent` 即可。

### `system_prompt`（系统提示）

| 层 | 说明 |
|----|------|
| **是什么** | 交给模型的「角色与偏好说明」，例如「禁止心算、先查长度再加法」 |
| **在本文干什么** | 降低小模型选错工具、乱心算的概率；与 `tools=` 列表一起约束行为 |
| **怎么区分** | **不是强制指令**。模型仍可能不遵守——这是 Agent 的固有特性，不是框架 bug。真正「硬边界」是：没注册进 `tools=` 的函数，模型调不到；已注册的工具，模型仍可能选错或传错参 |

因此演示题常配合：**少注册干扰工具** + **prompt 写清步骤**，双管齐下，而不是只靠一句 system_prompt。

### Ollama 与 `ollama:模型名`

| 层 | 说明 |
|----|------|
| **是什么** | 本机跑开源大模型的工具。字符串 `"ollama:qwen2:7b"` 经 LangChain 的 `init_chat_model` 解析；实际对话走 **langchain-ollama** 包 |
| **在本文干什么** | 免云端 API Key，本地演示 Agent 与工具调用；`pyproject.toml` 里必须装好 `langchain-ollama` |
| **怎么区分** | Ollama 提供**模型能力**；工具逻辑仍是你写的 Python。只装 `langchain` 不装 `langchain-ollama` 时，`"ollama:..."` 可能初始化失败。小模型可能传错参数或选错工具，Observation 报错后有时会重试——这也是循环的价值 |

### 链式调用（人话）

上一步工具的 **Observation**，常成为下一步 **Action 的入参**。  
例：`get_word_length("agent") → 5`，再 `add(5, 10) → 15`。  
人脑里是「先 A 后 B」；Agent 版是模型读完多张工具名片后自己排顺序。

---

## 环境准备

- Python 3.12+  
- [uv](https://docs.astral.sh/uv/)（也可用 pip）  
- 本机已安装并启动 [Ollama](https://ollama.com/)，并拉取一个模型，例如：

```bash
ollama pull qwen2:7b
ollama list    # 确认列表里有该模型
```

无需 Docker。

---

## 从空目录复现

```bash
mkdir day15-react-agent && cd day15-react-agent
```

### `pyproject.toml`

```toml
[project]
name = "day15-react-agent"
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

### 最小可运行脚本 `demo_agent.py`

下面示例：先查单词字母数，再把结果加 10。故意只注册需要的工具，并在 system_prompt 里写清「用加法」，减少小模型选错工具（记住：prompt **劝得动**，但**强不成**）。

```python
"""ReAct 风格 Agent：create_agent + @tool + Ollama。"""

from __future__ import annotations

import os

from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage, ToolMessage

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


def _text(content) -> str:
    return content if isinstance(content, str) else str(content)


def print_react_trace(messages: list) -> None:
    """把消息流映射回 Thought / Action / Observation。

    Answer 只取「最后一条无 tool_calls 的 AIMessage」，避免把中间推理文误标成最终答案。
    """
    step = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                for call in msg.tool_calls:
                    step += 1
                    print(f"Thought {step}: 模型决定调用 {call['name']}")
                    print(f"Action {step}: {call['name']}({call['args']})")
                # 若同条消息里还有自然语言，当作中间推理，不要标成 Answer
                text = _text(msg.content).strip() if msg.content else ""
                if text:
                    print(f"(中间文本) {text}")
        elif isinstance(msg, ToolMessage):
            print(f"Observation: {msg.content}")

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            text = _text(msg.content).strip() if msg.content else ""
            if text:
                print(f"Answer: {text}")
            break


def main() -> None:
    question = "单词 agent 有几个字母？把结果加10"

    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[get_word_length, add],
        system_prompt=(
            "你是严谨的助手。需要长度或加法时必须调用工具，禁止心算。"
            "先 get_word_length，再用返回的整数调用 add。"
        ),
    )

    print(f"Q: {question}\n")
    print("--- ReAct 轨迹 ---")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    print_react_trace(result["messages"])


if __name__ == "__main__":
    main()
```

### 运行与期望输出

```bash
uv run python demo_agent.py
```

期望类似（具体措辞因模型而异）：

```text
Q: 单词 agent 有几个字母？把结果加10

--- ReAct 轨迹 ---
Thought 1: 模型决定调用 get_word_length
Action 1: get_word_length({'word': 'agent'})
Observation: 5
Thought 2: 模型决定调用 add
Action 2: add({'a': 5, 'b': 10})
Observation: 15
Answer: ... 15 ...
```

对照阅读：

- `Action ... get_word_length` / `add` → 模型发起的行动  
- `Observation: 5` / `15` → 工具真实返回  
- 最终 `Answer` → 模型综合 Observation 后的自然语言答复  

换模型可设环境变量，例如：`OLLAMA_MODEL=qwen2.5-coder:7b uv run python demo_agent.py`。

---

## 工具名片从哪来（可选加深）

同一套函数，可以不经过 Agent，只看 LangChain 解析出的 schema：

```python
from langchain.tools import tool


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


t = get_word_length
print("名:", t.name)
print("说明:", t.description)
print("参数:", t.args_schema.model_json_schema().get("properties"))
```

你会看到：docstring → `description`；`word: str` → 类型 `string` 的必填参数。  
这就是模型选工具时读的「名片」。

---

## 新手坑（现象 → 原因 → 处理）

### 1. 写了 `add`，轨迹里却出现 `multiply`，答案变成 50

| | |
|--|--|
| **现象** | 问题是「加 10」，却调用乘法，`5 * 10 = 50` |
| **原因** | `add` 没加 `@tool`，或没放进 `tools=[...]`；同时 `system_prompt` 仍写着「调用 multiply」 |
| **处理** | `@tool` + 登记 `tools`；prompt / 工具列表与题目一致。演示加法题时可暂时不注册 `multiply`，减少干扰 |

### 2. 模型第一次把参数传成字符串或占位符

| | |
|--|--|
| **现象** | Observation 里出现校验错误，例如 `Input should be a valid integer` |
| **原因** | 小模型 tool calling 不稳，或没把上一步 Observation 正确填进下一步 |
| **处理** | 看后续是否自动重试并改对参数；换更强模型；在 system_prompt 强调「用上一步返回的整数」 |

### 3. `ollama:` 连不上 / 找不到模型 / 缺包

| | |
|--|--|
| **现象** | 连接错误、模型不存在，或初始化 chat model 失败 |
| **处理** | 确认 `ollama serve` 在跑；`ollama list` 里确有同名模型；`pyproject.toml` 已包含 **`langchain-ollama`** 并已 `uv sync`（`"ollama:..."` 依赖该集成） |

### 4. 轨迹里提前出现 `Answer:`，其实还没算完

| | |
|--|--|
| **现象** | 中间步骤模型吐了「我需要先查长度」之类文本，被打印成 Answer |
| **原因** | 若凡是「无 tool_calls 且 content 非空」就标 Answer，会把**中间推理**当成最终答复 |
| **处理** | 本文示例改为：**只把最后一条无 tool_calls 的 AIMessage 标为 Answer**；中间文本单独标 `(中间文本)` |

### 5. system_prompt 写了「必须用 add」，模型仍去心算或乱选工具

| | |
|--|--|
| **现象** | 提示写得很死，行为仍不稳定 |
| **原因** | system_prompt 是**软约束**，不是编译器级强制；小模型尤甚 |
| **处理** | 缩小 `tools=`、换更大模型、在 Observation 错误后依赖重试；生产环境再加校验与重试策略（本文不展开） |

---

## 本文边界

**做了什么**

- ReAct 三类标记与固定 RAG 链的对比  
- docstring / `@tool` / schema / `create_agent` 最小闭环  
- 本地 Ollama 可复现示例与链式工具调用  

**故意没展开（留给后续专题）**

- 天气 / SQL / HTTP 等真实业务工具  
- OpenAI Function Calling 协议细节  
- 对话 Memory、工具失败重试与降级  

---

## 延伸阅读

- [Lilian Weng · LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/)  
- [ReAct 论文](https://arxiv.org/abs/2210.03629)  
- [LangChain Agents 文档](https://docs.langchain.com/oss/python/langchain/agents)  

---

## 收束

记住三句话即可：

1. **ReAct** = 想一步、做一步、看结果，再决定下一步。  
2. **`@tool` + docstring + 类型** → 模型能读的工具名片；漏登记等于工具不存在。  
3. **`create_agent`** 是固定 LCEL 链之上的「可循环调用工具」入口——谁决定下一步，从代码换成了模型（在你提供的工具边界内）。
