# Day36–37 Lesson 1 — AutoGen 现役地图（先读再答）

> 挂钩上游：学习 `ConversableAgent`、`GroupChat` 等核心概念  
> **权威**： [AgentChat 文档](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/index.html) · [Migration Guide](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html) · [README](https://github.com/microsoft/autogen)  
> 本课**不跑代码**；先建立「原文名词 ↔ 现役 API」地图。

## 为什么课表不能照抄「旧教程」

| 年代 | 你常看到的写法 | 现状（官方） |
|------|----------------|--------------|
| **v0.2** | `from autogen import ConversableAgent`、`GroupChat`、`GroupChatManager` | 维护在 `0.2` 分支；**不要**当新课默认 |
| **现役 AgentChat（v0.4+）** | `autogen_agentchat` + `autogen_ext` | [stable 文档](https://microsoft.github.io/autogen/stable/) 主推；本课用这个 |
| **更远期** | Microsoft Agent Framework | README 写明：新项目优先；AutoGen 已 **maintenance mode** |

上游目标里的 **概念**（可对话 Agent、群聊协作）仍然成立；**类名/包名**必须用现役文档。

## 三层架构（现役）

```text
你写的应用代码
        │
        ▼
 autogen-agentchat     ← 任务向、好上手：AssistantAgent、RoundRobinGroupChat…
        │
        ▼
 autogen-core          ← 消息传递 / 运行时（多数时候先不用直接摸）
        │
        ▼
 autogen-ext           ← 模型客户端、工具、代码执行器（如 OpenAI / Ollama）
```

安装（官方 README）：

```bash
pip install -U "autogen-agentchat" "autogen-ext[openai]"
# 本练习目录用 uv 装同样两包
```

## 上游名词 → 现役等价（必背）

| 上游 / v0.2 说法 | 现役 AgentChat | 一句话 |
|------------------|----------------|--------|
| **ConversableAgent** | **`AssistantAgent`**（常用） | LLM 对话 Agent；可挂 tools |
| （人类代理等） | `UserProxyAgent` 等 | 人工介入 / 特殊角色 |
| **GroupChat** + Manager | **`RoundRobinGroupChat`** | 固定顺序轮流发言 |
| （更智能选人） | **`SelectorGroupChat`** | 模型/规则选下一个说话者 |
| `llm_config=...` | **`OpenAIChatCompletionClient`**（在 `autogen_ext`） | 模型客户端；Ollama 用 `base_url` |
| 同步 `initiate_chat` | **`async` `agent.run` / `team.run_stream`** | 现役以 asyncio 为主 |

> 口诀：**概念对齐上游，代码对齐 stable。**

## 最小心智模型

```text
单 Agent：  task ──► AssistantAgent.run() ──► 结果消息
多 Agent：  task ──► RoundRobinGroupChat([...agents], termination) ──► 轮流说话直到终止
```

终止条件常见：`TextMentionTermination("TERMINATE")`、`MaxMessageTermination(n)`（官方 teams / migration 示例）。

## 本课动手

读完本文件 + 扫一眼官方：

1. [Quickstart](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/quickstart.html)  
2. [Migration：ConversableAgent → 新 API](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/migration-guide.html)  

**不装依赖、不跑脚本。** 准备口述上面映射表两行。
