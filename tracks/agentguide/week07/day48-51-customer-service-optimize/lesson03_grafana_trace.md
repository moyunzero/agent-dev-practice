# Day48–51 Lesson 3 — Grafana 看面 + Trace 看单次（KP3）

> 挂钩上游：**监控: LangSmith + Grafana**  
> 复用：Day31 Grafana、Day29 LangSmith

## 本课唯一新点

| | Prometheus / Grafana | LangSmith（或等价 Trace） |
|--|----------------------|---------------------------|
| 回答什么 | 「这一阵整体怎样？」 | 「这一次请求慢在哪一步？」 |
| 颗粒 | 聚合：QPS、P99、错误率 | 单次：调用树 / 每步耗时 |
| 类比 | 路口车流量大屏 | 跟一辆车的行车记录仪 |

上游要「完整监控体系」= 两面都要：**面（大盘）+ 点（链路）**。

## 动手 A · Grafana 大盘

```bash
docker compose up -d
# 造一点流量
for i in 1 2 3 4 5; do
  curl -s http://127.0.0.1:8048/ask -H 'Content-Type: application/json' \
    -d '{"q":"订单 ORD-1001 到哪了？"}' > /dev/null
done
```

- Prometheus targets：http://127.0.0.1:19048/targets （`day48-cs` 应为 UP）  
- Grafana：http://127.0.0.1:13048 （admin / admin）→ 打开预置大盘 **Day48 · Customer Service API**

## 动手 B · 单次链路（等价 Trace）

本 API 暂无 LLM；用中间件一行日志 + `X-Request-ID` 作等价 Trace（真 LangSmith 等有模型调用再挂 Day29 环境变量）。

验收：响应头 ID 与 `docker compose logs api` 里 `request_id=` 对得上。 ✅
