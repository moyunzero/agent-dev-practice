# 学习轨登记（全仓入口）

> 新增学习项目时：**先在本表加一行**，再建目录 / 笔记 / 私人进度。  
> 本文件只登记「有哪些轨、公开落在哪」。维护者本地教法见 `docs/TEACHING.md`（若已纳入公开树则可点开）。

## 轨一览

| id | 公开名 | 阶段 | 公开代码 | 对外笔记 | 私人进度（不上传） | 状态 |
|----|--------|------|----------|----------|-------------------|------|
| `agentguide` | AgentGuide 开发岗 Day1–60 | ① | [`tracks/agentguide/`](../tracks/agentguide/)（内含 `week01/`…`week07/`） | [`notes/weekXX/`](../notes/) | 根目录 `PROGRESS.md` + 各 day `LEARN.md` | `available` |
| `harness` | WorkBuddy / Harness 深挖 | ② | [`tracks/harness/`](../tracks/harness/) | [`notes/learn-workbuddy/`](../notes/learn-workbuddy/) | `learn-workbuddy-main/`（gitignore） | `in_progress` |

## 怎么加第 3 条轨

```text
1. 本表加一行（id / 公开路径 / 笔记 / 私人进度 / 同步清单）
2. 建公开代码根（建议 tracks/<id>/）与 notes/<id>/
3. TEACHING.md「进度落盘」表补一行
4. 根 README「两条（或多条）学习轨」入口补一行
5. 私人跟练目录若不宜公开 → 写入根 .gitignore，只同步可跑切片到 tracks/
```

## 私人沙盒 vs 公开切片

| | 私人（可 ignore） | 公开（进 GitHub） |
|--|-------------------|-------------------|
| 用途 | LEARN、掌握检查、tutor-memory、完整上游副本 | 读者可跑的最小包 + 对外长文 |
| harness 例 | `learn-workbuddy-main/` | `tracks/harness/s0N_*` + `mini_workbuddy/` |
| agentguide 例 | 各 day 的 `LEARN.md` | 各 day 目录 + `notes/weekXX/` |

## 状态词

与公开文档一致：`available` / `in_progress` / `planned`。
