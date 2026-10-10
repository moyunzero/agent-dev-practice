# Day41 Lesson 2 — 带读并跑通三人旅行 Crew

> 第 1 课：三人职责与 `planner → guide → booker`。  
> 本课：写成代码并 `kickoff()`。

## 和 Day39–40 差在哪

| | Day39–40 | 今天 |
|--|----------|------|
| 人数 | 研究员 + 写手 | **planner + guide + booker** |
| 骨架 | `Crew` + `Process.sequential` | **同一个** |
| 接力 | `context=[research_task]` | 向导接规划；预订接 **两张**上游工单 |

## 对照脚本（打开 `step02_travel_crew.py`）

1. `LLM(model="ollama/...", base_url=...)` — 接本机 Ollama  
2. 三个 `Agent`：`role` / `goal` / `backstory`  
3. 三张 `Task`：`guide_task.context=[plan_task]`；`book_task.context=[plan_task, guide_task]`  
4. `Crew(..., process=Process.sequential)` → `kickoff()`  

API 入参/出参：见 [`lesson_api_cheatsheet.md`](./lesson_api_cheatsheet.md)（与 Day39–40 同栈）。

## 动手（本课唯一命令）

```bash
cd week06/day41-crewai-travel
uv sync
uv run python step02_travel_crew.py
```

**看什么**：日志里先后出现规划师 → 向导 → 预订专员；最后有一份建议清单（不是真订单）。
