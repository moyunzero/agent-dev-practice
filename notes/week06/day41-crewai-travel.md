# 用 CrewAI 搭「旅行规划师–本地向导–预订专员」三人小队

学习路线里常要求：用 CrewAI 做一个 **「旅行规划师–本地向导–预订专员」** 的 Multi-Agent 系统。  
概念上这是三人旅行小队；代码上继续用现役 CrewAI：**Agent + Task + Crew + Process.sequential**，不要退回 AutoGen 的轮流发言。

本文对齐官方 [Quickstart](https://docs.crewai.com/en/quickstart)、[LLM connections](https://docs.crewai.com/en/learn/llm-connections)，用本机 **Ollama** 跑通最小三人流水线：定骨架 → 补本地点 → 给出**建议预订**（假想清单，不调用真订票网站）。

## 你将会得到什么

1. 说清三人职责，以及为何拆成三个 Agent  
2. 用 sequential 工单流水线串起三张 Task  
3. 用 `context` 把上游结果交给下游（预订专员要接两张）  
4. 对照 AutoGen RoundRobin：何时用流水线、何时用轮流发言  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### Agent（谁）

| 层 | 说明 |
|----|------|
| **是什么** | 带角色设定的执行者 |
| **在本文干什么** | 三个：`planner` / `guide` / `booker`，各有 `role` / `goal` / `backstory` |
| **怎么区分** | 人 ≠ 事。Agent 是工种，Task 才是这一张工单 |

### Task（干什么）

| 层 | 说明 |
|----|------|
| **是什么** | 一张工单：描述 + 期望产出 + 指定给谁 |
| **在本文干什么** | `plan_task` → `guide_task` → `book_task` |
| **怎么区分** | 后一张要看见前面结果，必须写 `context=[...]`；CrewAI **不会**自动塞进全部聊天记录 |

### `context`（接力）

| 层 | 说明 |
|----|------|
| **是什么** | 告诉这张 Task：「做的时候请读这些上游 Task 的产出」 |
| **在本文干什么** | 向导接规划；预订接 **规划 + 向导** 两张 |
| **怎么区分** | 不是 AutoGen 群聊的消息历史；漏写 `context`，下游就只能靠自己猜 |

### Crew 与 Process.sequential

| 层 | 说明 |
|----|------|
| **是什么** | Crew 是剧组；sequential 是按 `tasks` 列表一个接一个做 |
| **在本文干什么** | `kickoff()` 开机；最终打印通常是**最后一张**工单的产出 |
| **怎么区分** | hierarchical 要经理 LLM/Agent；本文不用 |

### RoundRobin（对照，避免混）

| 层 | 说明 |
|----|------|
| **是什么** | AutoGen 里按名单**轮流发言**的开会规则 |
| **在本文干什么** | 不用它。旅行步骤有先后依赖，适合工单流水 |
| **怎么区分** | sequential=做完 A 再做 B；RoundRobin=A 说完 B 说，不一定「做完一张工单」 |

### Ollama 与 `LLM`

| 层 | 说明 |
|----|------|
| **是什么** | 本机大模型服务；CrewAI 用 `LLM` 接线 |
| **在本文干什么** | `LLM(model="ollama/<模型名>", base_url="http://127.0.0.1:11434")` |
| **怎么区分** | 模型名要带 `ollama/` 前缀；本文不接真实订票 API |

---

## 三人职责

| 角色 | Agent 名 | 干什么 | 不干什么 |
|------|----------|--------|----------|
| 旅行规划师 | `planner` | 定天数、节奏、主题 | 不列店名长清单、不下单 |
| 本地向导 | `guide` | 补 2～3 个可走的点 | 不推翻行程、不谈下单 |
| 预订专员 | `booker` | 建议订交通/住/票的短清单 | **不调用真订票网站**；不声称已订好 |

```text
用户短需求
   │
   ▼
plan_task（planner）
   │ context
   ▼
guide_task（guide）
   │ context（规划 + 向导）
   ▼
book_task（booker） → kickoff 结束
```

---

## 环境准备

- Python 3.10–3.13、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) 已启动，并已 `pull` 模型（下文默认 `llama3.1:8b`）  

```toml
# pyproject.toml
[project]
name = "day41-crewai-travel"
version = "0.1.0"
description = "Day41: CrewAI travel planner-guide-booker Multi-Agent"
requires-python = ">=3.10,<3.14"
dependencies = [
  "crewai[litellm]==1.15.20",
]
```

```bash
uv sync
curl -s http://127.0.0.1:11434/api/tags | head
```

---

## 完整示例

保存为 `step02_travel_crew.py`：

```python
from __future__ import annotations

import os

from crewai import Agent, Crew, LLM, Process, Task

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def main() -> None:
    llm = LLM(model=f"ollama/{MODEL}", base_url=BASE_URL)

    planner = Agent(
        role="旅行规划师",
        goal="根据短途需求写出极短的行程骨架",
        backstory="你只定天数、节奏、主题，不列店名、不下单。",
        llm=llm,
        verbose=True,
    )
    guide = Agent(
        role="本地向导",
        goal="按骨架补 2～3 个可走的点，短句即可",
        backstory="你熟悉本地街区与吃法，不推翻整份行程，不谈下单。",
        llm=llm,
        verbose=True,
    )
    booker = Agent(
        role="预订专员",
        goal="根据前两步给出建议预订的短清单",
        backstory="你只写假想的交通/住宿/门票建议，绝不声称已经订好。",
        llm=llm,
        verbose=True,
    )

    plan_task = Task(
        description=(
            "需求：杭州两天一夜，预算不高，偏轻松。"
            "写出行程骨架：天数、每天节奏、主题。中文短条。不要店名长清单。"
        ),
        expected_output="一份极短的中文行程骨架",
        agent=planner,
    )
    guide_task = Task(
        description=(
            "根据规划师的骨架，列出 2～3 个杭州可走的点（景点或街区或吃法）。"
            "每点一句中文。不要推翻骨架。"
        ),
        expected_output="2～3 条中文短推荐",
        agent=guide,
        context=[plan_task],
    )
    book_task = Task(
        description=(
            "根据规划师骨架和向导推荐，给出 3 条以内「建议预订」清单"
            "（例如交通/住宿/门票的假想项）。必须写明这是建议，不是已完成订单。"
        ),
        expected_output="不超过 3 条中文建议预订",
        agent=booker,
        context=[plan_task, guide_task],
    )

    crew = Crew(
        agents=[planner, guide, booker],
        tasks=[plan_task, guide_task, book_task],
        process=Process.sequential,
        verbose=True,
    )

    print("=== 旅行小队 kickoff（planner → guide → booker）===\n")
    result = crew.kickoff()
    print("\n=== 最终结果 ===")
    print(result)


if __name__ == "__main__":
    main()
```

### 关键 API

| API | 常用入参 | 何时用 |
|-----|----------|--------|
| `LLM` | `model`、`base_url` | 接 Ollama |
| `Agent` | `role`、`goal`、`backstory`、`llm` | 三个工种 |
| `Task` | `description`、`expected_output`、`agent`、`context` | 工单与接力 |
| `Crew.kickoff` | `agents`、`tasks`、`process=Process.sequential` | 开机 |

### 运行与期望

```bash
uv run python step02_travel_crew.py
```

**期望**：日志先后出现规划师、向导、预订专员；最终是「建议预订」，并写明不是已完成订单。  
本地小模型可能编造店名或景点——本文验收的是**协作结构**，不是攻略真实性。

---

## 新手向坑

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 连不上模型 | Ollama 未开；模型名少了 `ollama/` | `ollama serve`；核对 `OLLAMA_MODEL` |
| 预订清单对不上向导 | `book_task.context` 漏了 `guide_task` | 写成 `[plan_task, guide_task]` |
| 内容又长又假 | 小模型不守短输出 | 收紧 `expected_output`；仍以结构为准 |
| 想改成 RoundRobin | 框架混用 | 本系统是 CrewAI 工单流，不要套 AutoGen 开会规则 |

---

## 边界

**做了**：三人角色、sequential 三工单、`context` 接力、本机 Ollama、与 RoundRobin 对照。  

**没做**：真实搜索/订票工具、hierarchical、CrewAI Flows、框架大对比（通常在后续日）。

---

## 小结

旅行三人小队的落地，核心仍是四件套，只是工单变成三张：

1. 规划定骨架 · 向导补点 · 预订给建议  
2. `Process.sequential` 保证先后依赖  
3. `context` 决定下游能看见谁  

*系列笔记 · Agent 工程跟练 · Week 6 Day 41*
