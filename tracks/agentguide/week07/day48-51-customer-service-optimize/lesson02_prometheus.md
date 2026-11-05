# Day48–51 Lesson 2 — Prometheus 指标（KP2）

> 挂钩上游：**监控: Prometheus**  
> 复用：Week5 Day30（Instrumentator + `/metrics`）

## 本课唯一新点（接到客服 API）

应用自己露出一行行**原料数字**；QPS / 延迟 / 错误率是后人用这些原料算出来的。

| 你想知道的 | `/metrics` 里常见原料 | 怎么读 |
|------------|----------------------|--------|
| QPS（每秒请求数） | `*_requests_total`（Counter，只增） | 对时间求导 ≈ rate |
| 延迟 | `*_request_duration_*`（Histogram） | 看分位 / 桶 |
| 错误率 | 带 `status` 的请求计数 | 5xx / 总数 |

验收：Compose 里的 API 能 `curl /metrics`，打几次 `/ask` 后相关行数字变大。
