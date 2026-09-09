# Day39–40 Lesson 3 — 掌握检查（先回顾再答）

> 上游目标：学习 Agent / Task / Crew / Process，并运行官方示例。  
> 仅考已讲内容。答完后做一个小改动并说明为何生效。

## 先回顾（30 秒）

| 要点 | 一句话 |
|------|--------|
| 四件套 | Agent=谁 · Task=干什么 · Crew=剧组 · Process=怎么排 |
| 本课 Process | `Process.sequential`（按 tasks 列表顺序） |
| hierarchical | 还要 `manager_llm` 或 `manager_agent` |
| vs AutoGen | CrewAI ≈ 任务流水线；AutoGen RoundRobin ≈ 对话轮转 |
| Ollama | `LLM(model="ollama/...", base_url=...)` |

## 掌握题（≥3）

1. Agent / Task / Crew / Process 各是什么？谁包含谁？  
2. `Process.sequential` 和 `Process.hierarchical` 差在哪？本课用哪个？  
3. 和 Day36–38 的 AutoGen RoundRobin 比，CrewAI 编排更像「对话轮流」还是「任务流水线」？  

## 小改动（二选一，改完跑一次并说明）

A. 把写手 Task 的 `expected_output` 改成要求「不超过 12 个字」，观察口号是否变短。  
B. 去掉 `write_task` 的 `context=[research_task]`，跑一次，说说写手还能否稳定用上研究员要点（以及你看到的现象）。
