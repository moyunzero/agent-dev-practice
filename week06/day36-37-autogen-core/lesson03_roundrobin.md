# Day36–37 Lesson 3 — 两个助手轮流说话（从零讲）

> 上一课：一个助手问脑子、回答你。  
> 本课：请 **两个助手**，按固定顺序轮流发言——这就是上游说的 **GroupChat** 在现役里的常见写法：`RoundRobinGroupChat`。

---

## 1. 生活类比

会议室里两个人轮流发言，**主持人按名单顺序点名**（不争论谁先说）：

1. **写手**先说：写一句产品口号  
2. **评审**再说：觉得行就回 `APPROVE`，不行就给一句修改建议  
3. 再轮到写手……直到有人说出 `APPROVE`，或发言次数够了就结束  

「按名单轮流」= **RoundRobin**（轮转）。

```text
任务进入会议室
   → 写手说话
   → 评审说话
   → 写手说话
   → …
直到：有人说 APPROVE，或达到最大条数
```

---

## 2. 本课新词（只有这几个）

### 团队 / Team（这里就是群聊）

| 层 | 说明 |
|----|------|
| **是什么** | 把多个助手放进同一个「会议室」一起完成任务 |
| **在本课干什么** | `RoundRobinGroupChat([写手, 评审], …)` |
| **怎么区分** | 上一课只有一个助手；本课是**编排谁先谁后** |

### 轮转群聊 RoundRobinGroupChat

| 层 | 说明 |
|----|------|
| **是什么** | 按名单顺序轮流发言的会议室规则 |
| **在本课干什么** | 写手 → 评审 → 写手 → … |
| **怎么区分** | 还有一种「谁合适谁说」叫 `SelectorGroupChat`；本课**先不学** |

### 什么时候停？（终止条件）

| 名字 | 人话 |
|------|------|
| `TextMentionTermination("APPROVE")` | 有人话里出现 `APPROVE` 就散会 |
| `MaxMessageTermination(6)` | 消息太多也强制散会（防止小模型一直扯下去） |

两个条件用 `|` 连起来：**满足任意一个就停**。

### Console

| 层 | 说明 |
|----|------|
| **是什么** | 官方提供的「把对话一条条打印到终端」的小工具 |
| **在本课干什么** | `await Console(team.run_stream(task=...))` |
| **怎么区分** | 上一课我们自己 `print`；本课用 Console 更清楚看到谁在说话 |

---

## 3. 对照脚本（打开 `step03_roundrobin_two_agents.py`）

人话步骤：

1. 仍用同一个 Ollama「接线员」  
2. 雇两个助手：`writer`、`critic`（规矩写在 `system_message`）  
3. 定停会规则：出现 APPROVE **或** 消息达到上限  
4. 建轮转会议室，丢进任务  
5. 用 Console 看他们轮流说话  
6. `close` 接线员  

**每个类/方法的入参、出参、何时用**：见同目录  
[`lesson_api_cheatsheet.md`](./lesson_api_cheatsheet.md)  
（依据官方 AgentChat / Conditions / Console / Ollama 文档 + 本目录锁定的 0.7.5 签名，不是野路子总结。）

---

## 4. 动手

```bash
cd week06/day36-37-autogen-core
uv run python step03_roundrobin_two_agents.py
```

**看什么**：终端里会交替出现 `writer` 和 `critic` 的名字；最后应因 `APPROVE` 或条数上限结束。

跑完后用自己的话答（下一条消息再问你）：谁先说话？什么情况下会停？
