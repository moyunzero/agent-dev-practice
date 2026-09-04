# Day35 Lesson 5 — Week5 地图 + 掌握检查

> 挂钩：周度总结 + 确认「模拟故障 → 工具链定位」已闭环  
> 本课无新脚本；对照本周 Day29–34 + 今日演练口述。

## Week5 工具链一张图

```text
出故障了？
  │
  ├─ 容器还活着？     Day32–33 Docker / Compose（ps / health / 服务名 DNS）
  ├─ 整体坏多少？     Day30 Metrics → Day31 Grafana（趋势何时开始）
  ├─ 这一枪细节？     Day34 JSON 日志（path/status/duration_ms/request_id）
  ├─ 海量按字段搜？   Day35 加码 A：ES 存 + Kibana Discover
  └─ Agent 哪一环慢？ Day29 Trace（LangSmith 树）
```

口诀（第 1 课）：**Metrics 看面 → Logs 看点 → Trace 看路径**；Docker 先确认活着。

## 今日演练回顾（你已做过）

| 步骤 | 你做了什么 |
|------|------------|
| 注入 | `FAULT=slow` / `error` 重启 API |
| 定位 | 看 `duration_ms` vs `status`（慢≠一定 5xx） |
| 检索 | seed → ES；Kibana `status:500` / `fault:slow` |

## 掌握题（≥3 · 仅考已讲）

见 `LEARN.md`，下方由教练抽问。
