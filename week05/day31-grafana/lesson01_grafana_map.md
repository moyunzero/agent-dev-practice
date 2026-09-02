# Day31 Lesson 1 — Grafana 地图（先读再答）

```text
FastAPI (Day30)
  └── GET /metrics     ← 应用「吐」指标文本
        ▲
        │ scrape（定期拉取）
Prometheus Server      ← 存成时间序列，可用 PromQL 查
        ▲
        │ Data source（Grafana 问 Prometheus 要数）
Grafana
  └── Dashboard（大盘）
        └── Panel（一块图：折线 / 数字 / 表格…）
```

## 三个角色

| 组件 | 是什么 | 在今天干什么 |
|------|--------|--------------|
| **应用 `/metrics`** | 进程内 Counter/Histogram 的文本快照 | Day30 已做好；今天继续当「数据源源头」 |
| **Prometheus** | 定时 scrape、存历史、支持 `rate()` 等查询 | Compose 里跑一个；配置指向宿主机 API |
| **Grafana** | 可视化与大盘 UI | **安装**（Compose）+ **建简单 Dashboard** |

## 易混对照

| 说法 | 对 | 错 |
|------|----|----|
| Grafana 自己存指标？ | 一般**不**；它问 Data source | 以为装了 Grafana 就有 QPS 历史 |
| Prometheus vs `/metrics` | Server 刮取并**存时间**；`/metrics` 是**当前快照** | 二者是同一个东西 |
| Dashboard vs Panel | Dashboard = 一页大盘；Panel = 上面一块图 | 混为一谈 |

## 和 Day29 / Day30 的分工

| | Day29 Trace | Day30 Metrics | Day31 Grafana |
|--|-------------|---------------|---------------|
| 问题 | 这次慢在哪一步？ | 数字原料暴露了吗？ | **一眼看趋势** |

---

读完后回答教练 3 道抽问即可过第 1 课。本课**不要求**先起 Docker。
