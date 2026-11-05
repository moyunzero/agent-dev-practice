# Day34 Lesson 1 — JSON 日志地图（先读再答）

```text
应用 ──打一行──► stdout（一行一个 JSON）
                      │
                      │ Filebeat / Logstash / 采集器
                      ▼
                 Elasticsearch（可按字段搜索）
                      │
                      ▼
                   Kibana（查、画图）
```

ELK = Elasticsearch + Logstash（或 Beats）+ Kibana。  
今天**不装** ELK，但日志要长成 ELK **好吞** 的样子：JSON。

## 结构化 vs print

| | `print("用户问了 hello")` | JSON 结构化日志 |
|--|---------------------------|-----------------|
| 机器可读 | 差（自然语言） | 好（字段固定） |
| 搜索 | 全文糊弄 | 按 `path` / `status` / `request_id` 过滤 |
| 多行/换行 | 易打乱采集 | **一行一条**事件 |

示例一行：

```json
{"event":"request_done","path":"/ask","method":"GET","status":200,"duration_ms":52,"q":"hello"}
```

## 常见字段（本课会用到）

| 字段 | 干什么 |
|------|--------|
| `event` / `msg` | 发生了什么 |
| `path` / `method` | 哪个接口 |
| `status` | HTTP 状态 |
| `duration_ms` | 耗时 |
| `request_id`（可选） | 把同一次请求的多行日志串起来 |
| `level` / `timestamp` | 级别与时间（库常自动加） |

## 和 Trace / Metrics 的分工

| | 日志 | Trace (Day29) | Metrics (Day30) |
|--|------|---------------|-----------------|
| 问什么 | 「这条请求细节/错误上下文」 | 「这次链路哪步慢」 | 「过去 5 分钟 QPS/错误率」 |

---

读完后回答抽问。本课**先不写代码**。
