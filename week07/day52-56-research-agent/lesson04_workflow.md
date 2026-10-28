# Day52–56 Lesson 4 — 顺序工作流 + 中间产出（KP4）

> 挂钩上游：**工作流实现**；设计顺序工作流，并记录每一步的中间产出  
> 复用：Day41 `Process.sequential` + `Task(context=[...])`

## 本课唯一新点

三人按固定顺序跑；后一张 Task 用 `context` 吃前面的结果。  
每步结果还要**看得见**（打印或落盘），不能只剩最终报告。

```text
搜集 Task → 笔记 A（落盘 intermediate/01_research.md）
  → 分析 Task（context=[搜集]）→ 指标稿 B（02_analysis.md）
  → 撰写 Task（context=[搜集, 分析]）→ 报告（03_report.md + write_report_file）
```

| | sequential + context | 三人一起抢 |
|--|----------------------|------------|
| 顺序 | 固定：搜集 → 分析 → 撰写 | 不定 |
| 交接 | 下一任读上一任产出 | 容易丢交接物 |
| 审计 | 中间文件可对账 | 只看最终稿难查「分析做没做」 |
