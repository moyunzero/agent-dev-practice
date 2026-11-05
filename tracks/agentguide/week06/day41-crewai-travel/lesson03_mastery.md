# Day41 Lesson 3 — 掌握检查（先回顾再答）

> 上游目标：实现「旅行规划师–本地向导–预订专员」Multi-Agent 系统。  
> 仅考已讲内容。答完后做一个小改动并说明为何生效。

## 先回顾（30 秒）

| 要点 | 一句话 |
|------|--------|
| 三人 | planner 骨架 · guide 补点 · booker 建议预订（假想） |
| 顺序 | `plan_task → guide_task → book_task` |
| 接力 | `context=[上游 Task]`；预订接两张 |
| 骨架 | 仍是 `Crew` + `Process.sequential` + `kickoff()` |
| vs AutoGen | sequential=工单流水；RoundRobin=开会轮流发言 |

## 掌握题（≥3）

1. 三个 Agent 各干什么？三张 Task 谁先谁后、靠什么接力？  
2. 为什么本课用 sequential 而不是 RoundRobin？  
3. `book_task` 的 `context` 要接谁？只接一张会怎样？  

## 小改动（二选一，改完跑一次并说明）

A. 把需求改成另一个短途（例如「上海一天，只要吃」），看三人是否仍按顺序干活。  
B. 去掉 `book_task` 的 `guide_task`（只留 `plan_task`），观察预订清单是否更空、更不像向导推荐。
