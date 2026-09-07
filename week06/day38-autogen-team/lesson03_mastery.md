# Day38 Lesson 3 — 掌握检查（先回顾再答）

> 上游目标：实现「研究员–程序员–测试员」Multi-Agent 系统。  
> 仅考本课已讲内容。答完后做**一个小改动**并说清为何生效。

## 先回顾（30 秒）

| 要点 | 一句话 |
|------|--------|
| 三人职责 | researcher 拆需求 · coder 写短代码 · tester 用例 / APPROVE |
| 会议室 | 仍是 Day36–37 的 `RoundRobinGroupChat`（不是新 API） |
| 多出来的 | 多一个 `AssistantAgent` + 名单顺序改三人 |
| 共享状态 | 群聊消息历史 |
| 停会 | `APPROVE` 或 `MaxMessageTermination` |

你终端里已看到：`researcher` → `coder` → `tester`，且 tester 说了 `APPROVE` 就散会 ✅

## 掌握题（≥3）

1. 研究员 / 程序员 / 测试员各负责什么？为什么拆成三个 Agent？  
2. 本课用 RoundRobin 时，三人固定发言顺序是什么？对话「状态」存在哪？  
3. `TextMentionTermination` 与 `MaxMessageTermination` 在三人系统里各防什么？  

## 小改动（二选一，改完跑一次并说明）

A. 把 `MaxMessageTermination(9)` 改成 `4`，观察是否更早结束。  
B. 把任务改成另一个短需求（例如「华氏→摄氏」），看三人是否仍按顺序说话。
