# Day39–40 Lesson 1 — CrewAI 四件套地图（先读再答）

> 挂钩上游：**学习 Agent, Task, Crew, Process 的概念，并运行官方示例**  
> 权威：[CrewAI Docs](https://docs.crewai.com/) · [Quickstart](https://docs.crewai.com/quickstart)  
> 本课**不跑代码**；先建立「四件套」心智模型。Day41 旅行小队今天不展开。

## 生活类比：一家小剧组拍短片

| CrewAI 概念 | 类比 | 一句话 |
|-------------|------|--------|
| **Agent** | 演员/工种 | 有角色（role）、目标（goal）、背景故事（backstory）的人 |
| **Task** | 一场戏的任务单 | 要干什么、期望交出什么；通常指定给某个 Agent |
| **Crew** | 整组剧组 | 把 agents + tasks 装在一起，点「开机」就干活 |
| **Process** | 拍摄流程规矩 | 按任务顺序拍（sequential），还是有导演临时分派（hierarchical） |

```text
若干 Agent（人）
      +
若干 Task（事）  ──装配──►  Crew（剧组）
                              │
                         Process（怎么排活）
                              │
                         kickoff() 开机
```

## 和 AutoGen（Day36–38）对照（先讲清，免混）

| | AutoGen AgentChat（已学） | CrewAI（本课） |
|--|---------------------------|----------------|
| 常见味道 | **对话轮转**（谁说话） | **任务流水线**（先做啥后做啥） |
| 会议室 | `RoundRobinGroupChat` | `Crew` + `Process` |
| 停会 | Termination 条件 | 任务做完 / Process 跑完 |
| 角色写法 | `system_message` | `role` / `goal` / `backstory` |

口诀：**AutoGen 像开会轮流发言；CrewAI 像按工单流水作业。** 两边都是 Multi-Agent，API 不要混用。

## 四个词展开（是什么 / 本文干什么 / 怎么区分）

### Agent

| 层 | 说明 |
|----|------|
| **是什么** | 带角色设定的智能体 |
| **在本文干什么** | 官方常用字段：`role`、`goal`、`backstory`；可挂 `llm` |
| **怎么区分** | 不是 Task；Agent 是「谁」，Task 是「干什么」 |

### Task

| 层 | 说明 |
|----|------|
| **是什么** | 一件具体工作：描述 + 期望产出 |
| **在本文干什么** | `description`、`expected_output`、指定 `agent=`；可用 `context=[前一个Task]` 接上游结果 |
| **怎么区分** | 一个 Agent 可被多个 Task 指派；Task 挂在 Crew 的任务列表里按 Process 执行 |

### Crew

| 层 | 说明 |
|----|------|
| **是什么** | agents + tasks 的容器与执行入口 |
| **在本文干什么** | `Crew(agents=[...], tasks=[...], process=...)`，然后 `kickoff()` |
| **怎么区分** | Crew 是整组；单个 Agent 自己不算完整「官方示例」闭环 |

### Process

| 层 | 说明 |
|----|------|
| **是什么** | Crew 内部怎么排任务顺序/谁管谁 |
| **在本文干什么** | 本课主练 **`Process.sequential`**：按 `tasks` 列表顺序一个接一个 |
| **怎么区分** | **`Process.hierarchical`**：更像有经理分派（官方要求配 `manager_llm` / `manager_agent`）；本课只口述差别，不深挖 |

```text
Process.sequential（本课）:

  Task1（Agent A） → Task2（Agent B） → … → 结束

Process.hierarchical（知道即可）:

  经理看任务 → 分派给合适的 Agent → …（需要经理 LLM/Agent）
```

## 本课动手

1. 通读本文件  
2. 准备用自己的话回答下面抽问  

**不装依赖、不跑脚本。** Lesson 2 再写最小 Crew。
