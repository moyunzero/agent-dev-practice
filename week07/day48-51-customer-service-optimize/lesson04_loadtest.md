# Day48–51 Lesson 4 — 压测读 QPS / P99（KP4）

> 挂钩上游：**性能: QPS > 200, P99 < 500ms**  
> 复用：Week4 Day28 Locust

## 本课唯一新点

| 指标 | 人话 | 上游阈值 |
|------|------|----------|
| QPS / RPS | 每秒处理多少请求 | > 200 |
| P99 | 最慢那 1% 有多慢 | < 500ms |

压测是**量尺**：先读出数字，再解释达不达标、瓶颈在哪。达不到也要有报告，不能假装没测。

## 动手

```bash
# API 已在 Compose :8048
uv sync
uv run locust -f locustfile.py --host http://127.0.0.1:8048 \
  --headless -u 50 -r 10 -t 30s
```

读报告末尾：**Requests/s**（≈QPS）、**99%ile**（≈P99）、失败率。
对照上游：QPS>200 且 P99<500ms；写一句是否达标 + 可能瓶颈。
