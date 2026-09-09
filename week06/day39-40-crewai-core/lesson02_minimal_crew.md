# Day39–40 Lesson 2 — 带读并跑通最小 Crew

> 第 1 课：四件套地图。  
> 本课：写成代码并 `kickoff()`——官方风格最小 **sequential** 示例（Ollama）。

---

## 1. 脚本主路径（打开 `step02_minimal_crew.py`）

```text
LLM(ollama/模型) 
  → 两个 Agent（role/goal/backstory）
  → 两个 Task（后一个 context=[前一个]）
  → Crew(..., process=Process.sequential)
  → result = crew.kickoff()
```

和 AutoGen 对照：这里**不是**轮流聊天室，而是 **Task1 做完 → Task2 做** 的工单流水线。

---

## 2. 关键点读（对照官方）

| 步骤 | 代码里 | 官方口径 |
|------|--------|----------|
| 本地模型 | `LLM(model="ollama/...", base_url=...)` | [LLM connections · Ollama](https://docs.crewai.com/en/learn/llm-connections) |
| Agent | `role` / `goal` / `backstory` / `llm=` | Role–Goal–Backstory |
| Task | `description` / `expected_output` / `agent=` / `context=` | 后任务可读前任务产出 |
| Crew | `agents` + `tasks` + `process=Process.sequential` | 按任务列表顺序执行 |
| 开机 | `crew.kickoff()` | 返回整组结果 |

入参/出参细节：见 [`lesson_api_cheatsheet.md`](./lesson_api_cheatsheet.md)。

---

## 3. 动手（本课唯一命令）

```bash
cd week06/day39-40-crewai-core
uv sync
# 可选：export OLLAMA_MODEL=llama3.1:8b
uv run python step02_minimal_crew.py
```

**看什么**：verbose 日志里先后出现研究员任务、写手任务；最后打印一句口号（或等价最终结果）。

跑完用自己的话答抽问。
