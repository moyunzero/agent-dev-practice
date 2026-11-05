# Day36–37 Lesson 4 — 掌握检查（先回顾再答）

> 只考**已经讲过**的内容。不会的先翻讲义，不要猜。

## 复习地图（人话）

```text
单助手：接线员 OllamaChatCompletionClient
        → AssistantAgent
        → run(task) → TaskResult

多助手：两个 AssistantAgent
        → RoundRobinGroupChat（按名单轮流）
        → run_stream + Console（边跑边看）
        → 散会：说出 APPROVE 或 消息太多
```

上游旧名 ↔ 现役：

| 上游 / 旧 | 现役 |
|-----------|------|
| ConversableAgent | AssistantAgent |
| GroupChat | RoundRobinGroupChat（本课） |

包：`autogen-agentchat` + `autogen-ext[ollama]`（不要 v0.2 `from autogen import ...`）

API 细节：`lesson_api_cheatsheet.md`

## 掌握题（请用自己的话答）

见 `LEARN.md` 三道；答完即可。
