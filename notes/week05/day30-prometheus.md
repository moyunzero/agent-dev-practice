# 用 Prometheus 暴露 FastAPI 的 QPS、延迟与错误率（含缓存命中自定义指标）

接口已经能跑，压测也能打出数字，但线上还常问：

> 过去 5 分钟每秒多少请求？P99 延迟怎样？错误率飙了吗？缓存到底命中多少？

这类问题靠「单次请求的 Trace」不够——需要的是**一段时间上的趋势指标**。  
**Prometheus** 生态的做法是：应用进程里用 Counter / Histogram 记账，通过 **`/metrics`** 吐出标准文本；采集端定期来刮取（scrape）。

本文用 **FastAPI + prometheus-fastapi-instrumentator** 自动暴露 HTTP 层的 QPS / 延迟 / 错误率原料，再用 **prometheus_client.Counter** 加一个业务指标：**缓存命中 / 未命中**。不装 Grafana、也不强依赖本机跑满 Prometheus Server——`curl /metrics` 就能验收。

## 你将会得到什么

1. 分清 **Counter / Histogram / Gauge**，并映射到 QPS、延迟、错误率  
2. 一行 Instrumentator 挂上 `/metrics`，用 curl 读出请求计数与耗时桶  
3. 自定义 `cache_lookups_total{result="hit|miss"}`，打两次相同问句看到 hit 增加  
4. 说清 **指标 vs 链路追踪**（趋势 vs 单次）各自解决什么问题  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### 指标监控（Metrics）与 Prometheus

| 层 | 说明 |
|----|------|
| **是什么** | 用可聚合的数字描述系统健康：**吞吐、延迟分布、错误比例**等。Prometheus 是常见的时序指标方案：应用暴露、Server 刮取、再用查询语言算趋势 |
| **在本文干什么** | FastAPI 进程暴露 `/metrics`；你用 curl 读文本，确认 QPS/延迟/错误率的**原料**已在 |
| **怎么区分** | **压测报告**是「某次试验的结果」；**指标**是服务持续暴露、可被长期刮取的活数据。本文不展开 Grafana 大盘 |

```text
客户端 ──HTTP──► FastAPI
                   │ Instrumentator 记次数 / 耗时 / 状态码
                   │ 业务代码 .inc() 自定义 Counter
                   ▼
              GET /metrics  →  Prometheus 文本
                   ▲
         （可选）Prometheus Server 定期 scrape
```

### Counter（计数器）

| 层 | 说明 |
|----|------|
| **是什么** | **只增不减**的累计值（进程重启才归零）。适合「发生了多少次」这类事件 |
| **在本文干什么** | `http_requests_total`（Instrumentator）、`cache_lookups_total`（自定义） |
| **怎么区分** | 要「每秒多少」不要直接读绝对值，而用 **`rate(counter[窗口])`** 看增速。别用 Counter 记「当前在线人数」 |

### Histogram（直方图）

| 层 | 说明 |
|----|------|
| **是什么** | 把每次观察值（如耗时）打进预设的时间桶（bucket），同时保留 `_sum` / `_count` |
| **在本文干什么** | `http_request_duration_seconds_*`：延迟分布的原料，后续可算近似 P50/P99 |
| **怎么区分** | **Gauge 记最后一次延迟** ≠ P99。分位需要分布；Histogram（或 Summary）才是正路 |

### Gauge（仪表）

| 层 | 说明 |
|----|------|
| **是什么** | **可升可降**的当前水位：队列长度、内存、并发连接数 |
| **在本文干什么** | 本文核心指标不用 Gauge；对比时用来说明「别把累计事件做成 Gauge」 |
| **怎么区分** | 温度计 vs 里程表：水位用 Gauge，历史累计用 Counter |

### QPS / 延迟 / 错误率（业务说法 → 指标）

| 业务说法 | 怎么从指标得到 | 常用类型 |
|----------|----------------|----------|
| **QPS**（≈RPS） | `rate(http_requests_total[1m])` | Counter |
| **延迟（P99 等）** | `histogram_quantile(0.99, …)` | Histogram |
| **错误率** | `rate(5xx) / rate(全部)` | Counter（常用 `status` label） |

### `/metrics` 与 exposition 格式

| 层 | 说明 |
|----|------|
| **是什么** | HTTP 端点返回的 **Prometheus 文本**：`# HELP` / `# TYPE` + `metric_name{labels} value` |
| **在本文干什么** | `Instrumentator().expose(app, endpoint="/metrics")`；验收时 `curl` 这一页 |
| **怎么区分** | `/metrics` 是**快照**；趋势要靠采集端按时间序列存。不装 Server 也能先确认「暴露成功」 |

### FastAPI Instrumentator

| 层 | 说明 |
|----|------|
| **是什么** | [prometheus-fastapi-instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)：中间件自动记 HTTP 请求指标并暴露端点 |
| **在本文干什么** | 一行 `instrument(app).expose(...)` 覆盖上游要求的 **QPS / 延迟 / 错误率原料** |
| **怎么区分** | `instrument` = 开始记录；`expose` = 挂出 `/metrics`。它**不替代**业务自定义指标 |

### 自定义业务指标（缓存命中）

| 层 | 说明 |
|----|------|
| **是什么** | 用 `prometheus_client.Counter` 自己声明、在业务分支 `.inc()` |
| **在本文干什么** | `cache_lookups_total{result="hit\|miss"}`，模拟答案缓存 |
| **怎么区分** | HTTP 层不知道「算不算缓存命中」；业务语义必须手埋。命中率 = `rate(hit) / rate(all)`，原料仍是 Counter |

### 和链路追踪（如 LangSmith）的分工

| | 链路追踪 | Prometheus 指标 |
|--|----------|-----------------|
| 粒度 | **单次**请求内每一步 | **一段时间**整体 |
| 典型问题 | 这次慢在模型还是工具？ | 过去 5 分钟 QPS/P99/错误率？ |

两者叠加，不互相替换。

---

## 要解决什么问题

| 只有日志 / Trace | 加上 `/metrics` |
|------------------|-----------------|
| 知道某次很慢 | 知道**最近整体**是否变慢、变错 |
| 难算 QPS | Counter + rate 就是吞吐原料 |
| 缓存「感觉有用」 | hit/miss Counter 能量化命中 |

---

## 环境准备（从零开始）

需要：Python 3.11+、[uv](https://docs.astral.sh/uv/)（或 pip）。

```bash
mkdir day30-prometheus && cd day30-prometheus
```

`pyproject.toml`：

```toml
[project]
name = "day30-prometheus"
version = "0.1.0"
description = "Expose FastAPI QPS / latency / error metrics via Prometheus"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "prometheus-fastapi-instrumentator>=7.0.0",
]
```

```bash
uv sync
```

官方参考：[Prometheus Python Client](https://github.com/prometheus/client_python)、[FastAPI Instrumentator](https://github.com/trallnag/prometheus-fastapi-instrumentator)。

---

## 完整代码

将下面保存为 `main_api.py`：

```python
"""FastAPI + Instrumentator + 自定义缓存命中 Counter。"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="day30-prometheus")

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

CACHE_LOOKUPS = Counter(
    "cache_lookups_total",
    "Ask answer cache lookups",
    labelnames=("result",),
)

_ANSWER_CACHE: dict[str, str] = {}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    if q in _ANSWER_CACHE:
        CACHE_LOOKUPS.labels(result="hit").inc()
        return {"q": q, "answer": _ANSWER_CACHE[q], "cache": "hit"}

    CACHE_LOOKUPS.labels(result="miss").inc()
    await asyncio.sleep(0.05)
    answer = f"echo:{q}"
    _ANSWER_CACHE[q] = answer
    return {"q": q, "answer": answer, "cache": "miss"}


@app.get("/fail")
async def fail() -> dict:
    raise HTTPException(status_code=500, detail="boom")
```

---

## 这段代码在干什么

| 片段 | 作用 |
|------|------|
| `Instrumentator().instrument(app).expose(...)` | HTTP 自动指标 + `/metrics` |
| `CACHE_LOOKUPS = Counter(..., labelnames=("result",))` | 业务 Counter：hit / miss |
| `/ask` 分支里 `.inc()` | 每次查找推一次；同 `q` 第二次走 hit |
| `/fail` | 造 5xx，方便在 `http_requests_total{status="5xx"}` 看到错误 |

```text
GET /ask?q=hello
  ├─ miss → Counter{result="miss"} += 1，算答案，写入缓存
  └─ 再 GET 同 q → hit → Counter{result="hit"} += 1
同时 Instrumentator 对每次 HTTP 更新 requests / duration
```

---

## 启动与验证

**终端 A：**

```bash
uv run uvicorn main_api:app --port 8030
```

**终端 B：**

```bash
curl -s 'http://127.0.0.1:8030/ask?q=hello'   # cache: miss
curl -s 'http://127.0.0.1:8030/ask?q=hello'   # cache: hit
curl -s 'http://127.0.0.1:8030/ask?q=other'   # miss
curl -s http://127.0.0.1:8030/fail              # 500，属预期
curl -s http://127.0.0.1:8030/metrics | rg 'http_requests_total|http_request_duration|cache_lookups'
```

**期望（数量级）：**

- `http_requests_total{handler="/ask",status="2xx"}` ≥ 3  
- `http_requests_total{...status="5xx"}` ≥ 1  
- `http_request_duration_seconds_*` 有 bucket / sum / count  
- `cache_lookups_total{result="miss"}` ≈ 2，`{result="hit"}` ≈ 1  

有上述行 = **核心指标已暴露**；装 Prometheus Server 刮取是下一步增强，不是今天的验收底线。

---

## 踩过的坑

### 1. 只看 uvicorn 日志以为「监控好了」

**现象**：access log 有 200/500，以为指标已就绪。  
**原因**：日志 ≠ Prometheus exposition。  
**处理**：必须 `curl /metrics`，看到 `# TYPE ... counter/histogram` 才算暴露成功。

### 2. 改完代码数字不变

**现象**：加了 `CACHE_LOOKUPS` 但 `/metrics` 没有。  
**原因**：uvicorn 未加载新进程（没 `--reload` 时要重启）。  
**处理**：Ctrl+C 后重新 `uvicorn`。

### 3. 用 Gauge 存「命中率」

**现象**：想直接 `gauge.set(0.85)`。  
**原因**：丢失累计与时间窗口灵活性。  
**处理**：Counter 记 hit/miss，查询时用 `rate` 算比率。

### 4. `handler="none"` 的 4xx

**现象**：莫名其妙多了 4xx。  
**原因**：浏览器或其它客户端打了 `/` 等不存在路径。  
**处理**：按 `handler` / `status` label 过滤；不影响 `/ask` 结论。

---

## 取舍与未做之事

| 做了 | 故意没做 |
|------|----------|
| Instrumentator 暴露 QPS/延迟/错误率原料 | 本机完整 Prometheus Server + 告警规则 |
| 自定义缓存 hit/miss Counter | Grafana 大盘（常见下一主题） |
| curl 验收 `/metrics` | Token 消耗埋点（同属自定义 Counter，模式相同） |
| 内存字典当玩具缓存 | 接 Redis 真缓存（与指标主题正交） |

---

## 小结

- **QPS ← Counter + rate**；**延迟 ← Histogram**；**错误率 ← 错误/总请求两个累计**。  
- **`/metrics`** 暴露的是进程内指标快照；和 Trace 分工：趋势 vs 单次。  
- Instrumentator 管 HTTP；业务语义（缓存命中）要 **自己 Counter + `.inc()`**。  
- 验收口令：curl 出 `http_requests_*`、`http_request_duration_*`、`cache_lookups_total`。  

下一步常见是用 **Grafana** 把这些时间序列画成大盘——指标先暴露，可视化才有数据可连。

---

*系列笔记 · Agent 工程跟练 · Week 5 Day 30*
