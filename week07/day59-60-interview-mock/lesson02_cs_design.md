# Day59–60 Lesson 2 — 客服 RAG 系统设计口述（KP2）

> 挂钩：高并发/低延迟/监控；本仓 Day43–51

## 本课唯一新点

把四步骨架**套进客服**，每步落到本仓组件，不要空谈「上大模型」。

| 步 | 客服版要点 |
|----|------------|
| 澄清 | 订单类 vs FAQ；QPS/P99；查不到是否 `need_human` |
| 架构 | 客户端 → FastAPI `/ask` → **先 Postgres** → 未命中 **FAQ** → 返回 |
| 瓶颈/监控 | DB/FAQ 慢；Locust QPS/P99；`/metrics` + Grafana；`request_id` |
| 权衡 | 例：先精确查库再模糊 FAQ（准 > 瞎生成）；Compose 整栈 vs 只起库 |

本仓可引用数字：本机 Locust 库路径 QPS≈281，P99≈250ms。
