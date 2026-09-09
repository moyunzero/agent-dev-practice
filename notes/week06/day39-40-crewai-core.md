# 用 CrewAI 跑通 Agent / Task / Crew / Process 最小示例

Multi-Agent 另一条常见路线是 **CrewAI**：把工作拆成「谁来做」和「做什么」，再装进一个 Crew 按 Process 执行。  
本文对齐官方 [CrewAI Docs](https://docs.crewai.com/)、[Quickstart](https://docs.crewai.com/en/quickstart)、[LLM connections](https://docs.crewai.com/en/learn/llm-connections)，用本机 **Ollama** 跑一个最小 **sequential** 示例：研究员列要点 → 写手写一句口号。

## 你将会得到什么

1. 说清 Agent / Task / Crew / Process 四件套，以及谁包含谁  
2. 分清 `Process.sequential` 与 `Process.hierarchical`  
3. 对照 AutoGen 的「对话轮转」，理解 CrewAI 更偏「任务流水线」  
4. 用官方 `LLM(model="ollama/...", base_url=...)` 接本机模型并 `kickoff()`  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### Agent（智能体 / 「谁」）

| 层 | 说明 |
|----|------|
| **是什么** | 带角色设定的执行者 |
| **在本文干什么** | 用 `role` / `goal` / `backstory` 定义研究员与写手，并挂上同一个本地 `llm` |
| **怎么区分** | Agent 是「人」；Task 是「事」。不要把两段设定糊成一个对象 |

官方常用 **Role–Goal–Backstory**：角色（干什么工种）、目标（追求什么结果）、背景（工作风格与边界）。

### Task（任务 / 「干什么」）

| 层 | 说明 |
|----|------|
| **是什么** | 一张工单：要做什么、期望交出什么 |
| **在本文干什么** | `description` + `expected_output` + `agent=`；写手任务用 `context=[research_task]` 读取上游产出 |
| **怎么区分** | 改 `expected_output` 会约束**该 Task** 的产出形态，不会自动改另一个 Task |

### Crew（剧组）

| 层 | 说明 |
|----|------|
| **是什么** | agents + tasks 的容器，以及执行入口 |
| **在本文干什么** | `Crew(agents=[...], tasks=[...], process=...)`，然后 `kickoff()` |
| **怎么区分** | 单个 Agent 不等于完整示例；官方闭环通常是 Crew 开机 |

### Process（排活规矩）

| 层 | 说明 |
|----|------|
| **是什么** | Crew 内部怎样安排任务顺序 / 谁管谁 |
| **在本文干什么** | 使用 **`Process.sequential`**：按 `tasks` 列表一个接一个 |
| **怎么区分** | **`Process.hierarchical`** 更像经理分派；官方要求再配 `manager_llm` 或 `manager_agent`。本文不深挖 hierarchical |

```text
Process.sequential（本文）:

  Task1（研究员） → Task2（写手） → 结束
```

### Ollama 与 `LLM`

| 层 | 说明 |
|----|------|
| **是什么** | Ollama 在本机提供大模型；CrewAI 用 `LLM` 类描述「用哪个模型、连哪里」 |
| **在本文干什么** | `LLM(model="ollama/<模型名>", base_url="http://127.0.0.1:11434")` |
| **怎么区分** | 模型名要带官方文档里的 `ollama/` 前缀；`base_url` 指向本机 Ollama，不是 OpenAI 云端 |

非原生厂商通道会走 LiteLLM；安装时可用官方推荐的 `crewai[litellm]` 额外依赖。

### 和 AutoGen（对话轮转）对照

| | AutoGen RoundRobin | CrewAI（本文） |
|--|--------------------|----------------|
| 味道 | 会议室谁接着说话 | 工单：先做啥后做啥 |
| 停法 | Termination 条件 | 任务按 Process 跑完 |
| 角色写法 | `system_message` | `role` / `goal` / `backstory` |

口诀：**AutoGen 像开会轮流发言；CrewAI 像按工单流水作业。** API 不要混用。

---

## 最小架构

```text
若干 Agent（人）+ 若干 Task（事）
        ──装配──►  Crew
                     │
                Process.sequential
                     │
                kickoff()
```

---

## 环境准备

- Python 3.10–3.13、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) 已启动，并已 `pull` 模型（下文默认 `llama3.1:8b`）  

```toml
# pyproject.toml
[project]
name = "day39-40-crewai-core"
version = "0.1.0"
description = "Day39-40: CrewAI Agent Task Crew Process core concepts"
requires-python = ">=3.10,<3.14"
dependencies = [
  "crewai[litellm]==1.15.20",
]
```

```bash
uv sync
# 可选：
# export OLLAMA_MODEL=llama3.1:8b
# export OLLAMA_BASE_URL=http://127.0.0.1:11434
```

确认 Ollama：

```bash
curl -s http://127.0.0.1:11434/api/tags | head
```

---

## 完整示例：研究员 → 写手（sequential）

保存为 `step02_minimal_crew.py`：

```python
from __future__ import annotations

import os

from crewai import Agent, Crew, LLM, Process, Task

MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def main() -> None:
    llm = LLM(model=f"ollama/{MODEL}", base_url=BASE_URL)

    researcher = Agent(
        role="产品研究员",
        goal="把产品需求拆成极短、可执行的要点",
        backstory="你擅长把模糊需求写成三条以内的清晰条目，从不写长文。",
        llm=llm,
        verbose=True,
    )
    writer = Agent(
        role="文案写手",
        goal="根据要点写出一句短、好记的中文口号",
        backstory="你只输出一句口号，不解释、不加前后缀。",
        llm=llm,
        verbose=True,
    )

    research_task = Task(
        description=(
            "为「本地笔记 App」列出恰好 3 条产品卖点要点（中文短句）。"
            "不要写口号，不要编号以外的废话。"
        ),
        expected_output="恰好 3 条中文短要点",
        agent=researcher,
    )
    write_task = Task(
        description=(
            "根据研究员给出的 3 条要点，写一句中文产品口号。"
            "只要一句，要短、好记。"
        ),
        expected_output="一句中文口号",
        agent=writer,
        context=[research_task],
    )

    crew = Crew(
        agents=[researcher, writer],
        tasks=[research_task, write_task],
        process=Process.sequential,
        verbose=True,
    )

    print("=== Crew kickoff（sequential：先研究后写）===\n")
    result = crew.kickoff()
    print("\n=== 最终结果 ===")
    print(result)


if __name__ == "__main__":
    main()
```

### 关键 API（对照官方）

| API | 常用入参 | 行为 / 出参 | 何时用 |
|-----|----------|-------------|--------|
| `LLM` | `model`、`base_url` | 模型客户端配置 | 接 Ollama / 自定义端点 |
| `Agent` | `role`、`goal`、`backstory`、`llm` | Agent 实例 | 定义不同职责的人 |
| `Task` | `description`、`expected_output`、`agent`、`context` | Task 实例 | 定义工单；`context` 接上游 |
| `Crew` | `agents`、`tasks`、`process` | 剧组；`kickoff()` 出结果 | 官方最小闭环 |
| `Process.sequential` | 枚举值 | 按 tasks 顺序执行 | 本文默认 |

### 运行与期望

```bash
uv run python step02_minimal_crew.py
```

**期望**：日志里先出现研究员 Task，再出现写手 Task；最后打印一句口号（措辞随模型变化）。  
本地小模型可能不完全遵守「恰好 3 条 / 只一句」——演示的是**结构**（四件套 + sequential），不是文案质量竞赛。

---

## 新手向坑

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 连不上模型 / LiteLLM 报错 | Ollama 未开；缺 `crewai[litellm]`；模型名少了 `ollama/` 前缀 | `ollama serve`；按上文依赖安装；核对 `OLLAMA_MODEL` |
| 改了 `expected_output` 却像没生效 | 改错了 Task（约束只作用在挂了该字段的那张工单） | 确认改的是写手还是研究员那一条 |
| 去掉 `context=[research_task]` | 写手看不到上游要点，口号更易跑偏 | 需要接力时保留 `context` |
| 只改成 `Process.hierarchical` 就挂 | 缺少经理配置 | 按官方补 `manager_llm` 或 `manager_agent`；入门先用 sequential |

---

## 边界：做了什么 / 故意没做什么

**做了**：四概念、sequential 最小 Crew、Task `context`、本机 Ollama、与 AutoGen 对照。  

**没做**：hierarchical 实战、旅行三人小队（常见于后续实战日）、复杂 Tools、CrewAI Flows。

---

## 小结

学 CrewAI 核心，抓四件套即可：

1. **Agent** 定谁 · **Task** 定干什么  
2. **Crew** 装配 · **Process** 定顺序  
3. 本机用官方 **`LLM(..., base_url=...)`** + **`kickoff()`**

*系列笔记 · Agent 工程跟练 · Week 6 Day 39–40*
