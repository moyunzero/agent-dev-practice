# Day39–40 — 本课 API 说明书（CrewAI 1.15.x · 对照官方）

> 权威：  
> [Quickstart](https://docs.crewai.com/en/quickstart) ·  
> [LLM connections](https://docs.crewai.com/en/learn/llm-connections) ·  
> [Crafting Agents](https://docs.crewai.com/en/guides/agents/crafting-effective-agents)

## `LLM`

| | |
|--|--|
| **干什么** | 告诉 CrewAI 用哪家模型、连哪里 |
| **本课入参** | `model`（Ollama 用 `"ollama/<模型名>"`）、`base_url`（如 `http://127.0.0.1:11434`） |
| **出参** | LLM 配置对象，传给 `Agent(llm=...)` |
| **何时用** | 不用默认云端 OpenAI、要接本机 Ollama 时 |

官方 Ollama 示例形态：`LLM(model="ollama/llama3.2", base_url="http://localhost:11434")`。

## `Agent`

| | |
|--|--|
| **干什么** | 定义「谁」——角色化执行者 |
| **常用入参** | `role`、`goal`、`backstory`；可选 `llm`、`verbose` |
| **出参** | Agent 实例，放进 `Crew(agents=[...])` 或挂到 `Task(agent=...)` |
| **何时用** | 需要不同职责的人时 |

## `Task`

| | |
|--|--|
| **干什么** | 定义「干什么」——工单 |
| **常用入参** | `description`、`expected_output`、`agent`；可选 `context=[上游 Task]` |
| **出参** | Task 实例，放进 `Crew(tasks=[...])` |
| **何时用** | 把工作拆成可串行（或可分层）的步骤时 |

## `Crew` + `Process` + `kickoff`

| | |
|--|--|
| **干什么** | 装配剧组并按 Process 执行 |
| **常用入参** | `agents`、`tasks`、`process=Process.sequential`（或 `.hierarchical`）、`verbose` |
| **出参** | `kickoff()` 返回 Crew 运行结果（可读最终文本） |
| **何时用** | 官方最小闭环：有人 + 有事 + 开机 |

**hierarchical**：需要 `manager_llm` 或 `manager_agent`（本课不练，只记差别）。
