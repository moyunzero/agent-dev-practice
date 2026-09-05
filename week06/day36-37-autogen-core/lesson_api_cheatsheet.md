# Day36–37 — 本课用到的 API 说明书（依据官方文档 / 已安装 0.7.5 源码签名）

> **权威来源（跟练时以这些为准，不要背野路子博客）**  
> - AgentChat 教程 / Quickstart：https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/  
> - Agents 参考：https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.agents.html  
> - Conditions 参考：https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.conditions.html  
> - UI `Console`：https://microsoft.github.io/autogen/stable/reference/python/autogen_agentchat.ui.html  
> - Ollama 客户端：https://microsoft.github.io/autogen/stable/reference/python/autogen_ext.models.ollama.html  
> - Migration（RoundRobin 示例）：https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html  
>
> 下面「签名」与本练习目录锁定的 **`autogen-agentchat==0.7.5` / `autogen-ext==0.7.5`** 一致（`inspect.signature`）。

人话总览：

| 你想做的事 | 用谁 |
|------------|------|
| 接通本机 Ollama | `OllamaChatCompletionClient` |
| 雇一个会聊天的助手 | `AssistantAgent` |
| 让**一个**助手完成任务，一次拿齐结果 | `await agent.run(...)` |
| 让**多个**助手按名单轮流说话 | `RoundRobinGroupChat` + `run_stream` |
| 决定何时散会 | `TextMentionTermination` / `MaxMessageTermination` |
| 把流式对话漂亮打到终端 | `Console(...)` |
| 用完关掉模型连接 | `await model_client.close()` |

---

## 1. `OllamaChatCompletionClient`（接线员）

**从哪来**：`from autogen_ext.models.ollama import OllamaChatCompletionClient`

**干什么**：连本机（或远程）Ollama，帮助手发「聊天补全」请求。文档要求：Ollama 已安装，并且模型已 `pull`。

**构造（官方 docstring 要点）**：

| 参数 | 要不要 | 含义 |
|------|--------|------|
| `model` | 要 | 用哪个 Ollama 模型名，如 `llama3.1:8b` |
| `host` | 可选 | 模型服务地址；默认本机 Ollama |
| `model_info` | 有时要 | 描述模型能力；**若模型不在官方预置列表里，文档写明 Required** |
| `options` / `response_format` | 可选 | 额外 Ollama 选项 / 结构化输出 |

签名（0.7.5）：`OllamaChatCompletionClient(**kwargs)`（具体键见 `BaseOllamaClientConfiguration`）。

**什么时候用**：助手需要「脑子」时先建客户端，再传给 `AssistantAgent(..., model_client=...)`。

**`close()`**：`async` 关闭连接。官方 Quickstart 在跑完后调用 `await model_client.close()`。

---

## 2. `AssistantAgent`（助手）

**从哪来**：`from autogen_agentchat.agents import AssistantAgent`

**干什么**：预设的「能用模型、也能挂工具」的聊天助手（官方称 kitchen-sink / 原型与教学常用）。

**构造签名（0.7.5，节选本课用到的）**：

```text
AssistantAgent(
  name: str,                          # 必填：助手名字（群聊里用来区分是谁在说话）
  model_client: ChatCompletionClient, # 必填：接线员（Ollama / OpenAI 客户端等）
  *,
  tools=None,                         # 可选：工具列表（本课不用）
  description="An agent that...",     # 可选：给编排器用的文字简介
  system_message="You are a helpful AI assistant...",  # 可选：系统提示（规矩）
  model_client_stream=False,          # 可选：是否流式吐 token
  ...                                 # 还有 memory / handoffs / max_tool_iterations 等，本课不展开
)
```

**什么时候用**：需要「一个带角色设定、会调用模型说话」的参与者时。

---

## 3. `agent.run` / `agent.run_stream`（让单个助手干活）

官方对所有 AgentChat Agent 的共性说明（教程）：  
- `run`：给定 task，返回 **`TaskResult`**  
- `run_stream`：同样干活，但**边跑边产出消息流**，最后一项仍是结果  

### `await agent.run(...)`

| | 说明（文档 / 签名） |
|--|---------------------|
| **入参 `task`** | `str` **或** 单条消息 **或** 消息列表 **或** `None` |
| **入参 `cancellation_token`** | 可选，用来立刻取消 |
| **入参 `output_task_messages`** | 默认 `True` |
| **出参** | **`TaskResult`** |

### `TaskResult` 里有什么（0.7.5 字段）

| 字段 | 含义 |
|------|------|
| `messages` | 这次跑出来的消息列表 |
| `stop_reason` | 为何停下（可能为 `None`） |

**什么时候用 `run`**：只要最终结果、自己 `print` 即可（第 2 课）。  
**什么时候用 `run_stream`**：想边生成边看；常和 `Console` 一起用（官方 Quickstart 示例）。

---

## 4. `RoundRobinGroupChat`（轮转会议室）

**从哪来**：`from autogen_agentchat.teams import RoundRobinGroupChat`

**干什么（类文档原文意译）**：团队里的参与者**按轮转顺序**发言，并把消息发布给其他人。

**构造签名（0.7.5，本课相关）**：

| 参数 | 要不要 | 含义 |
|------|--------|------|
| `participants` | 要 | 参与者列表：`ChatAgent` 或嵌套 `Team` |
| `termination_condition` | 可选 | 终止条件（见下） |
| `max_turns` | 可选 | 最大轮次；官方说明可与 termination **任一触发就停** |
| `name` / `description` | 可选 | 团队名与描述 |

**什么时候用**：固定顺序「A→B→A→B…」的多助手协作（对应上游 GroupChat 的常见落地）。

### `team.run_stream(...)`

| | 说明 |
|--|------|
| **入参 `task`** | 同 `agent.run`：字符串 / 消息 / 列表 / `None` |
| **出参** | **异步生成器**：中间是消息/事件，**最后一项是 `TaskResult`** |
| **注意** | 文档写：停下来后会 **reset** termination；流式 chunk 事件可能 yield 但不一定进最终 `TaskResult.messages` |

**什么时候用**：多助手对话要逐步看见每个人说了什么（第 3 课）。

---

## 5. 终止条件（什么时候散会）

### `TextMentionTermination`

```text
TextMentionTermination(text: str, sources: Sequence[str] | None = None)
```

| 参数 | 含义 |
|------|------|
| `text` | 消息里出现这段文字就终止（如 `"APPROVE"`） |
| `sources` | 可选；若指定，**只检查这些助手**发出的消息 |

**何时用**：希望某角色说出口令（APPROVE / TERMINATE）就结束。

### `MaxMessageTermination`

```text
MaxMessageTermination(max_messages: int, include_agent_event: bool = False)
```

| 参数 | 含义 |
|------|------|
| `max_messages` | 最多允许多少条消息 |
| `include_agent_event` | 默认 `False`：主要数 `BaseChatMessage`；`True` 时事件也计入 |

**何时用**：防止模型一直聊不停（第 3 课安全网）。

### 组合

官方 Migration 示例：`TextMentionTermination("TERMINATE") | MaxMessageTermination(10)`  
含义：**任一条件满足就停**。

---

## 6. `Console`（把流打印到终端）

**从哪来**：`from autogen_agentchat.ui import Console`

```text
await Console(stream, *, no_inline_images=False, output_stats=False, user_input_manager=None)
```

| 参数 | 含义 |
|------|------|
| `stream` | **必填**：来自 `run_stream`（或 `on_messages_stream`）的异步流 |
| `no_inline_images` | 可选；终端内联图片相关 |
| `output_stats` | 可选（实验性）；打印统计 |

| 返回 | 含义 |
|------|------|
| 流来自 `run_stream` | 返回最后的 **`TaskResult`** |
| 流来自 `on_messages_stream` | 返回 **`Response`** |

**何时用**：懒得自己 `async for` 打印时，官方推荐写法：`await Console(team.run_stream(task=...))`。

---

## 7. 和本课两份脚本的对应关系

| 脚本 | 调用链 |
|------|--------|
| `step02_assistant_hello.py` | `OllamaChatCompletionClient` → `AssistantAgent` → **`run`** → 看 `TaskResult` → `close` |
| `step03_roundrobin_two_agents.py` | 同一 client → 两个 `AssistantAgent` → `RoundRobinGroupChat` → **`Console(run_stream(...))`** → `close` |

读完这份再回头看脚本里的 1) 2) 3)，把「名字」和「入参/出参」对上号即可。
