# 把 FastAPI 日志打成 JSON：为接入 ELK 做准备

线上排障时，`print("出错了")` 几乎帮不上忙：采集器难解析，Kibana 也没法按 `status=500` 过滤。  
**结构化 JSON 日志**让每一行成为一条事件：字段固定、一行一条，Filebeat / Logstash 好吞，Elasticsearch 好索引。

本文用 **structlog** 把日志渲染成 JSON，再挂到 FastAPI 中间件，使每次请求在 **stdout** 打出可被 `jq` 解析的一行。今天**不安装**完整 ELK，但输出格式已按接入做好准备。

## 你将会得到什么

1. 说清 JSON 日志相对 `print` 的优势，以及和 ELK 的关系  
2. 用 structlog 的 `JSONRenderer` 打出一行一条 JSON  
3. 在 FastAPI 请求路径自动记录 `path` / `status` / `duration_ms` / `request_id`  
4. 用 curl + 看 uvicorn 终端完成验收  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### 结构化日志（Structured logging）

| 层 | 说明 |
|----|------|
| **是什么** | 用固定字段描述事件（键值对），而不是一整句自然语言 |
| **在本文干什么** | `log.info("request_done", path="/ask", status=200, ...)` |
| **怎么区分** | `print("用户访问了 /ask")` 给人看；结构化日志给**机器与检索系统**看 |

### JSON 日志行

| 层 | 说明 |
|----|------|
| **是什么** | 标准输出上**一行一个** JSON 对象 |
| **在本文干什么** | structlog `JSONRenderer()` 的产物 |
| **怎么区分** | 多行漂亮打印不利于多数日志采集；生产常用 **一行一条** |

```json
{"event":"request_done","path":"/ask","method":"GET","status":200,"duration_ms":0.53,"request_id":"...","level":"info","timestamp":"..."}
```

### ELK

| 层 | 说明 |
|----|------|
| **是什么** | Elasticsearch（存/搜）+ Logstash 或 Beats（采集）+ Kibana（查与可视化） |
| **在本文干什么** | 解释「为何 JSON」；**不**在本机起三件套 |
| **怎么区分** | 今天交付的是**日志形状**；明天若接 ELK，采集 stdout 即可，不必改业务语义 |

```text
FastAPI ──JSON 行──► stdout
                        │ 采集（Filebeat 等）
                        ▼
                   Elasticsearch
                        │
                     Kibana
```

### structlog

| 层 | 说明 |
|----|------|
| **是什么** | Python 结构化日志库；processors 流水线末尾可 `JSONRenderer` |
| **在本文干什么** | 配置 JSON 输出；中间件里打 `request_done` |
| **怎么区分** | 也可用标准 `logging` + JSON formatter / Loguru；模式相同——**字段化 + JSON 行** |

### `request_id`

| 层 | 说明 |
|----|------|
| **是什么** | 一次请求的关联 ID（可透传 `X-Request-Id`） |
| **在本文干什么** | 中间件生成或读取，写入每条请求日志 |
| **怎么区分** | 主要用途是**串起同一次请求的多行日志**，不只是「看起来唯一」 |

### 和 Trace / Metrics 的分工

| | 日志 | Trace | Metrics |
|--|------|-------|---------|
| 擅长 | 细节与错误上下文 | 单次链路哪步慢 | 一段时间 QPS/错误率 |

---

## 要解决什么问题

| 随便 print | JSON 日志 |
|------------|-----------|
| 难按字段搜 | Kibana 可按 `path`/`status` 过滤 |
| 换行打乱采集 | 一行一条事件 |
| 和监控脱节 | 与 Trace/Metrics 互补 |

---

## 环境准备（从零开始）

Python 3.11+、[uv](https://docs.astral.sh/uv/)。

```toml
# pyproject.toml
[project]
name = "day34-logging"
version = "0.1.0"
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

参考：[Python Logging](https://docs.python.org/3/howto/logging.html)、[structlog](https://www.structlog.org/)。

---

## 完整代码

### 最小 JSON 示例 `step02_json_logger.py`

```python
import logging
import sys
import structlog

logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
)
log = structlog.get_logger()
log.info("request_done", path="/ask", method="GET", status=200, duration_ms=52)
```

### FastAPI + 中间件 `main_api.py`（核心）

```python
import time, uuid, sys, logging
import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# configure_json_logging() 同 Lesson2，含 JSONRenderer …

app = FastAPI()
log = structlog.get_logger()

class RequestJsonLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            return response
        finally:
            log.info(
                "request_done",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status=response.status_code if response else 500,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                q=request.query_params.get("q"),
            )

app.add_middleware(RequestJsonLogMiddleware)

@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    return {"q": q, "answer": f"echo:{q}"}
```

---

## 这段代码在干什么

1. **processors 末尾 `JSONRenderer`**：前面加的 level/时间一并进 JSON  
2. **中间件 `finally`**：成功或异常都打请求收尾日志  
3. **字段**：`event`（由第一参数变成）+ `path`/`status`/`duration_ms`/`request_id`  
4. **写到 stdout**：与 HTTP 响应体分离——采集盯的是进程日志流  

---

## 启动与验证

```bash
uv run python step02_json_logger.py
# 可选：… | jq .
```

```bash
uv run uvicorn main_api:app --port 8034
```

另开终端：

```bash
curl -s 'http://127.0.0.1:8034/ask?q=hello'
curl -s http://127.0.0.1:8034/health
```

**期望（uvicorn 终端）**：每条请求一行 JSON，例如含 `"event":"request_done"`, `"path":"/ask"`, `"status":200`。  
**不要**把 curl 返回的 `{"q":"hello",...}` 当成「日志已 JSON」——那是业务 body。

---

## 踩过的坑

### 1. 只看 curl 响应

**原因**：响应体 ≠ 应用日志。  
**处理**：看跑 uvicorn 的终端 stdout。

### 2. `JSONRenderer` 不在最后

**现象**：输出不是纯 JSON 或字段缺失。  
**处理**：渲染器放在 processors **末尾**。

### 3. 把一切糊进一句字符串

**处理**：用关键字参数传字段，便于 ELK 索引。

### 4. 浏览器探针产生的 404

**现象**：`/`、`/json/version` 也有 JSON 行。  
**说明**：中间件记录了所有请求；属正常，过滤 `path` 即可。

---

## 取舍与未做之事

| 做了 | 故意没做 |
|------|----------|
| structlog JSON + FastAPI 中间件 | 本机起 Elasticsearch/Kibana |
| request_id / 耗时 / 状态字段 | 全量请求头、PII 脱敏策略生产化 |
| stdout 一行一条 | 多文件轮转、集中式采样率 |

---

## 小结

- **JSON 一行一条** = ELK 友好的日志形状。  
- **事件名 + 字段**；用中间件统一打请求收尾日志。  
- 验收：uvicorn stdout 可被 `jq` 解析，而不是自然语言 print。  

下一步常见是周度故障演练：结合 Trace、Metrics、日志一起定位——可观测三件套（链/指标/日志）与部署主线已齐。

---

*系列笔记 · Agent 工程跟练 · Week 5 Day 34*
