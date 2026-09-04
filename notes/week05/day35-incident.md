# 模拟一次线上故障：用可观测工具链定位问题（含最小 ES + Kibana）

接口「变慢了」或「报错了」时，如果只会盯着 HTTP 状态码或随便翻终端，很容易漏掉真相：  
**慢不一定是 5xx**，成功响应也可能拖了两秒。

本文做两件事：

1. **模拟故障**：用环境变量给 FastAPI 注入 `slow` / `error`，并打出结构化 JSON 请求日志  
2. **工具链定位**：按「面 → 点 → 路径」选信号；再把同形状 JSON 写入 **Elasticsearch**，用 **Kibana Discover** 按字段过滤  

不装完整 Logstash / Filebeat 也能闭环：用脚本把样例日志 PUT 进 ES，等价于「采集器吞了一行」。

## 你将会得到什么

1. 说清 Metrics / 日志 / Trace 各回答什么问题，延迟飙升时优先看谁  
2. 跑通可注入故障的最小 API，用 `duration_ms` 与 `status` 钉死 slow vs error  
3. Compose 起最小 ES + Kibana，按 `status:500` / `fault:slow` 检索  
4. 一张「可观测排障」地图，把链路追踪、指标、大盘、容器、JSON 日志串起来  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### 故障注入（Fault injection）

| 层 | 说明 |
|----|------|
| **是什么** | 故意让系统表现出「慢」或「挂」，用来练习排障，而不是等线上真炸 |
| **在本文干什么** | 环境变量 `FAULT=off|slow|error` 控制 `/ask` 行为 |
| **怎么区分** | 不是单元测试里的 mock；这里是**运行时**整条请求路径的可复现故障 |

### Metrics（指标）

| 层 | 说明 |
|----|------|
| **是什么** | 一段时间的聚合数字：QPS、延迟分位、错误率等 |
| **在本文干什么** | 排障口诀里的「面」：先确认整体是否真的变慢、趋势何时开始（常配合 Grafana） |
| **怎么区分** | 不知道「是哪一次请求」；要细节看日志，要链路步骤看 Trace |

### 结构化 JSON 日志

| 层 | 说明 |
|----|------|
| **是什么** | 一行一个 JSON 对象，字段固定（如 `path` / `status` / `duration_ms`） |
| **在本文干什么** | 中间件打 `request_done`；桌面排障时盯 uvicorn stdout；样例再写入 ES |
| **怎么区分** | `print("出错了")` 给人扫一眼；JSON 给机器索引与按字段过滤 |

### Trace（链路追踪）

| 层 | 说明 |
|----|------|
| **是什么** | 一次请求在系统内部的**步骤树**（模型调用、工具、下游 RPC 等） |
| **在本文干什么** | 地图里说明：Agent 多跳「哪一环慢」时再开 Trace（如 LangSmith） |
| **怎么区分** | 不是替代 Metrics；还没确认「面」上飙升时，先别一头扎进树 |

### Elasticsearch（ES）

| 层 | 说明 |
|----|------|
| **是什么** | 近实时搜索与分析引擎：文档入库后按字段建索引 |
| **在本文干什么** | 存 `day35-logs` 索引里的请求日志文档 |
| **怎么区分** | ES 负责**存与查**；给人点点点的是 Kibana，不是 ES 本身 |

### Kibana

| 层 | 说明 |
|----|------|
| **是什么** | Elastic 栈的可视化与探索界面 |
| **在本文干什么** | Discover 里写 KQL：`status:500`、`fault:slow` |
| **怎么区分** | 没有 ES 里的数据，Kibana 无米下锅；本文故意**不起 Logstash** |

### Data View（数据视图）

| 层 | 说明 |
|----|------|
| **是什么** | Kibana 里指向一组索引的「镜头」（索引模式 + 时间字段） |
| **在本文干什么** | 模式 `day35-logs*`，时间字段 `timestamp` |
| **怎么区分** | 不是再复制一份数据；只是告诉 Kibana「去哪读、时间轴用哪个字段」 |

### 信号对照（口诀）

| | Metrics | Logs | Trace |
|--|---------|------|-------|
| 粒度 | 聚合（面） | 单次事件（点） | 单次请求内的步骤（路径） |
| 擅长 | 坏了多少 / 多快 / 何时开始 | 这一枪细节 | 哪一环拖后腿 |

```text
出故障了？
  │
  ├─ 容器还活着？     Docker / Compose（ps / health）
  ├─ 整体坏多少？     Metrics → Grafana
  ├─ 这一枪细节？     JSON 日志（status / duration_ms / request_id）
  ├─ 海量按字段搜？   ES 存 + Kibana Discover
  └─ Agent 哪一环慢？ Trace
```

口诀：**Metrics 看面 → Logs 看点 → Trace 看路径**；容器先确认还活着。

---

## 要解决什么问题

| 只看 HTTP 状态码 | 本文做法 |
|------------------|----------|
| `slow` 仍是 200，会被当成「正常」 | 看 `duration_ms` + `fault` |
| 终端自然语言难搜 | JSON 字段固定；Kibana 可 `status:500` |
| 工具乱点 | 先面后点再路径 |

---

## 环境准备

- Python 3.11+、[uv](https://docs.astral.sh/uv/)  
- Docker Desktop（ES + Kibana；建议给 Docker ≥2GB 内存）  
- 端口：**8035**（API）、**19200**（ES）、**15601**（Kibana）——避开常见 9200/5601  

```toml
# pyproject.toml
[project]
name = "day35-incident"
version = "0.1.0"
description = "Incident simulation + JSON logs + minimal ES/Kibana"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",
  "structlog>=24.0.0",
]
```

```bash
uv sync
```

---

## 步骤 1：故障注入 API

环境变量 `FAULT` 在**进程启动时**读入；改完必须**重启** uvicorn。

| `FAULT` | `/ask` 行为 | 日志关键字段 |
|---------|-------------|--------------|
| `off` | 正常 200 | `duration_ms` 很小 |
| `slow` | sleep 后再 200 | **`duration_ms` 很大**，仍可能 `status=200` |
| `error` | `HTTPException` → 500 | **`status=500`**，耗时通常不大 |

完整 `main_api.py`：

```python
"""可注入故障的最小 FastAPI（JSON 请求日志）。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
import uuid

import structlog
from fastapi import FastAPI, HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

FAULT = os.getenv("FAULT", "off").strip().lower()
SLOW_SECONDS = float(os.getenv("SLOW_SECONDS", "2.0"))

app = FastAPI(title="day35-incident")


def configure_json_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


configure_json_logging()
log = structlog.get_logger()


class RequestJsonLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status = response.status_code if response is not None else 500
            log.info(
                "request_done",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=status,
                duration_ms=duration_ms,
                fault=FAULT,
                q=request.query_params.get("q"),
            )


app.add_middleware(RequestJsonLogMiddleware)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "fault": FAULT}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    if FAULT == "slow":
        await asyncio.sleep(SLOW_SECONDS)
        return {"q": q, "answer": f"echo:{q}", "fault": FAULT}
    if FAULT == "error":
        raise HTTPException(status_code=500, detail="injected fault: downstream boom")
    return {"q": q, "answer": f"echo:{q}", "fault": FAULT}
```

### 验证（看 uvicorn 终端，不是 curl 正文）

```bash
FAULT=off uv run uvicorn main_api:app --port 8035
# 另开终端：
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=a'

# Ctrl+C 后换慢故障再启：
FAULT=slow uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=b'
# 期望：HTTP 200，time≈2s；JSON 里 duration_ms 很大、fault=slow

FAULT=error uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=c'
# 期望：HTTP 500；JSON 里 status=500、fault=error
```

**钉死故障的两个信号**：`duration_ms`（认 slow）与 `status`（认 error）。要点：**慢 ≠ 一定 5xx**。

---

## 步骤 2：最小 ES + Kibana

`docker-compose.yml`（教学关闭安全；勿直接当生产）：

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.15.3
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - xpack.security.http.ssl.enabled=false
      - ES_JAVA_OPTS=-Xms512m -Xmx512m
    ports:
      - "19200:9200"
    healthcheck:
      test: ["CMD-SHELL", "curl -s http://127.0.0.1:9200 >/dev/null || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 30

  kibana:
    image: docker.elastic.co/kibana/kibana:8.15.3
    environment:
      - ELASTICSEARCH_HOSTS=http://elasticsearch:9200
      - XPACK_SECURITY_ENABLED=false
    ports:
      - "15601:5601"
    depends_on:
      elasticsearch:
        condition: service_healthy
```

```bash
docker compose up -d
curl -s http://127.0.0.1:19200 | head
```

用 `seed_to_es.py` 写入与请求日志**同形状**的三条样例（off / slow / error）。完整脚本见练习目录；核心是对 `http://127.0.0.1:19200/day35-logs/_doc/...` 做 PUT。

```bash
uv run python seed_to_es.py
```

打开 http://127.0.0.1:15601 ：

1. Stack Management → Data Views → Create：索引模式 **`day35-logs*`**，时间字段 **`timestamp`**  
2. Discover：时间范围要盖住样例时间；过滤 **`status:500`** 或 **`fault:slow`**  

### 实拍

Data View（索引模式 + 时间字段）：

![Data View day35-logs*](assets/day35/01-kibana-dataview-day35-logs.png)

Discover 过滤 `status:500`（命中 fault=error）：

![Discover status:500](assets/day35/02-discover-status-500.png)

Discover 过滤 `fault:slow`（仍是 200，但 duration_ms≈2005）：

![Discover fault:slow](assets/day35/03-discover-fault-slow.png)

收工：

```bash
docker compose down
```

---

## 新手向坑

| 现象 | 原因 | 处理 |
|------|------|------|
| `Failed to spawn: uvicorn` | 不在含 `.venv` 的项目目录跑 `uv run` | `cd` 到本练习目录再 `uv sync` / `uv run` |
| 改了 `FAULT` curl 仍是旧行为 | 旧进程还占着端口；或新进程没起来 | 先停旧 uvicorn；在正确目录重启 |
| Discover 0 条 | 时间范围太窄（如 Last 15 minutes）盖不住样例 `@timestamp` | 拉大到当天 / Absolute，或改 seed 时间 |
| 只看 HTTP 码觉得「没故障」 | `slow` 仍是 200 | 看 `duration_ms` / `time_total` |

---

## 边界（做了什么 / 故意没做什么）

| 做了 | 没做 |
|------|------|
| 可复现 slow / 5xx + JSON 日志定位 | 真实生产告警值班、多机混沌工程 |
| 最小 ES + Kibana 按字段搜 | 完整 Logstash 管道、Filebeat 必装 |
| 排障地图串起 Trace / Metrics / 日志 / 容器 | 本文不要求同时起全套 Grafana + LangSmith |

和「只把日志打成 JSON」的差别：多了 **采集入库（JSON → ES）** 与 **Kibana 检索**。形状仍是同一套字段。

---

## 小结

1. 延迟飙升：先 **Metrics/Grafana（面）**，再日志（点），Agent 多跳再 **Trace（路径）**  
2. 用 `FAULT` 注入；靠 **`duration_ms` + `status`** 区分 slow 与 error  
3. ES 存、Kibana 搜；`status:500` / `fault:slow` 即可见证「结构化日志为什么值得打」  

*系列笔记 · Agent 工程跟练 · Week 5 Day 35*
