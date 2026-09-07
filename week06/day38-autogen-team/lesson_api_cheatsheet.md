# Day38 — 本课 API 说明书（AgentChat 0.7.5 · 对照官方）

> 与 Day36–37 同栈。权威：  
> [Teams](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/teams.html) ·  
> [AssistantAgent](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/agents.html) ·  
> [Termination](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/termination.html) ·  
> [Ollama client](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/models.html)

## `OllamaChatCompletionClient`

| | |
|--|--|
| **干什么** | 连本机 Ollama，当「接线员」 |
| **常用入参** | `model`（如 `llama3.1:8b`） |
| **出参** | 客户端实例；用完 `await close()` |
| **何时用** | 每个要调模型的 Agent 都需要 `model_client` |

## `AssistantAgent`

| | |
|--|--|
| **干什么** | 可对话助手（≈ 上游 ConversableAgent） |
| **常用入参** | `name`（群聊里显示的名字）、`model_client`、`system_message`（角色规矩） |
| **出参** | Agent 实例，可放进 Team |
| **何时用** | 需要「有角色的说话者」时 |

## `RoundRobinGroupChat`

| | |
|--|--|
| **干什么** | 按名单顺序轮流发言的群聊 |
| **常用入参** | 参与者列表 `[agent, …]`；`termination_condition`（可选） |
| **出参** | Team；`run` / `run_stream(task=...)` 产出对话 |
| **何时用** | 固定顺序协作（本课：研究员→程序员→测试员） |

## `TextMentionTermination` / `MaxMessageTermination`

| | 入参要点 | 何时用 |
|--|----------|--------|
| `TextMentionTermination(text)` | 消息中出现该文本则停 | 测试员说 `APPROVE` |
| `MaxMessageTermination(max_messages)` | 消息条数上限 | 防本地小模型聊不停 |
| `A \| B` | 任一条件满足即停 | 本课两者都要 |

## `Console` + `run_stream`

| | |
|--|--|
| **干什么** | 把流式消息漂亮打印到终端（带说话者名字） |
| **用法** | `await Console(team.run_stream(task="..."))` |
| **何时用** | 想看清多人交替发言时（比自己 print 清晰） |
