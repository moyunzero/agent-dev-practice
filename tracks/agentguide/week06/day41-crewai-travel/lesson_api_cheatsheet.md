# Day41 — 本课 API 说明书（CrewAI 1.15.x · 对照官方）

> 与 Day39–40 同栈。权威：  
> [Quickstart](https://docs.crewai.com/en/quickstart) ·  
> [LLM connections](https://docs.crewai.com/en/learn/llm-connections)

## `LLM`

| | |
|--|--|
| **干什么** | 接哪家模型 |
| **本课入参** | `model="ollama/<名>"`、`base_url` |
| **出参** | 传给 `Agent(llm=...)` |
| **何时用** | 本机 Ollama |

## `Agent`

| | |
|--|--|
| **常用入参** | `role`、`goal`、`backstory`、`llm` |
| **何时用** | 定义规划师 / 向导 / 预订专员 |

## `Task`

| | |
|--|--|
| **常用入参** | `description`、`expected_output`、`agent`、`context=[上游 Task, ...]` |
| **何时用** | 工单；后一张要读前面结果时必须写 `context` |

## `Crew` + `Process.sequential` + `kickoff`

| | |
|--|--|
| **入参** | `agents`、`tasks`（顺序=执行顺序）、`process=Process.sequential` |
| **出参** | `kickoff()` 的最终文本（通常是最后一张 Task 的产出） |
| **何时用** | 按工单流水作业（本课） |
