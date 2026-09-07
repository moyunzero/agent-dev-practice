# Day38 Lesson 2 — 带读并跑通三人开发小队

> 第 1 课：三人职责与轮转顺序。  
> 本课：把职责写成三个 `AssistantAgent`，放进同一个 `RoundRobinGroupChat` 跑起来。

---

## 1. 和 Day36–37 差在哪（先讲清楚）

| | Day36–37 `step03` | 今天 `step02_dev_team.py` |
|--|-------------------|---------------------------|
| Agent 数量 | 2（writer / critic） | **3**（researcher / coder / tester） |
| 会议室 API | `RoundRobinGroupChat` | **同一个** |
| 名单顺序 | writer → critic | researcher → coder → tester |
| 终止 | `APPROVE` 或 `MaxMessageTermination(6)` | 同样；上限改为 **9**（三人一轮消息更多） |

骨架没变：**接线员 → 雇助手 → 定停会规则 → 建会议室 → `Console(run_stream)` → close**。

---

## 2. 对照脚本（打开 `step02_dev_team.py`）

按注释里的 1～6 步走：

1. `OllamaChatCompletionClient` — 接线员（入参 `model`；用完要 `close`）  
2. 三个 `AssistantAgent` — 必填大致：`name`、`model_client`、`system_message`（工牌规矩）  
3. `TextMentionTermination("APPROVE") | MaxMessageTermination(9)` — 任一满足就停  
4. `RoundRobinGroupChat([researcher, coder, tester], termination_condition=...)`  
5. `await Console(team.run_stream(task=...))` — 流式打印，看出是谁在说话  
6. `await model_client.close()`  

**入参 / 出参 / 何时用**：见同目录 [`lesson_api_cheatsheet.md`](./lesson_api_cheatsheet.md)（与 Day36–37 同栈 0.7.5，对照官方）。

**共享状态**：`run_stream` 过程中累积的消息；后发言者能看到前面的话。

---

## 3. 动手（本课唯一命令）

```bash
cd week06/day38-autogen-team
uv sync
uv run python step02_dev_team.py
```

**看什么**：

- 终端交替出现 `researcher` / `coder` / `tester`  
- 因 `APPROVE` 或消息上限结束  
- 小模型不一定立刻 APPROVE——所以才有条数上限  

跑完用自己的话答下面抽问。
