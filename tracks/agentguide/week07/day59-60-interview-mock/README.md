# Week 7–8 / Day 59–60 — 系统设计与面试 Mock

> **状态**：`available`  
> **长文教程**：[Agent 岗系统设计面试：四步骨架、两套案例与追问怎么答](../../../../notes/week07/day59-60-interview-mock.md)

## 今日目标

准备高频系统设计题，并进行 1v1 模拟面试。

## 前置

- 已完成 Day43–58（客服、投研、简历）或能讲述等价项目  
- 参考题库：[LLM 系统设计面试题](https://www.analyticsvidhya.com/blog/2024/04/rag-interview-questions/)

## 文件说明

| 文件 | 作用 |
|------|------|
| `design_skeletons.md` | 通用骨架 + 客服/投研口述提纲 |
| `followup_cards.md` | 性能/故障/幻觉追问卡 |
| `mock_debrief.md` | 1v1 Mock 复盘 |
| `README.md` | 本页 |

## 推荐顺序

| 步骤 | 动作 |
|:----:|------|
| 1 | 背四步骨架（`design_skeletons.md`） |
| 2 | 套客服 / 投研各讲一遍 |
| 3 | 练 `followup_cards.md` 三类追问 |
| 4 | 1v1 Mock + 写 `mock_debrief.md` |

## 验收命令（口述日）

```bash
cd tracks/agentguide/week07/day59-60-interview-mock
# 打开 design_skeletons.md / followup_cards.md / mock_debrief.md，确认：
# - 能不看稿说出：澄清 → 架构 → 瓶颈/监控 → 权衡
# - 客服含先库后 FAQ；投研含三人 sequential
# - mock_debrief 有优点 + 改进（如澄清补一致性）
```

**期望**：追问能指到本仓组件（Grafana / `request_id` / 重试降级 / `source` 或中间稿）。
