# 智能客服优化与部署：Compose 整栈、监控大盘与压测达标

核心功能跑通之后，简历上还缺三块：**能一键部署、能看见健康度、能量出吞吐与延迟**。  
本文承接「先查 PostgreSQL、再 FAQ 回退」的客服 API，把它补成 Compose 整栈（API + Postgres + Prometheus + Grafana），接上 `/metrics` 与单次请求日志，再用 Locust 读出 QPS / P99，并写清项目文档四件事。

## 你将会得到什么

1. 分清「只起库」和「整栈部署」；容器内用服务名连库  
2. 用 Instrumentator 露出 Prometheus 原料，并在 Grafana 上看 QPS / P99  
3. 用 `request_id` 日志当单次等价 Trace（与大盘配对）  
4. 用 Locust 压测，对照 QPS>200、P99<500ms 写结论  
5. 写出能让外人独立起栈、调 API、压测、看监控的 README  

---

## 零基础名词表

> 建议先读完再动手。每个词：**是什么 → 在本文干什么 → 怎么区分**。

### Compose 整栈 vs 只起库

| 层 | 说明 |
|----|------|
| **是什么** | Docker Compose 一次起多个服务；整栈 = API 和依赖都在 Compose 里 |
| **在本文干什么** | `postgres` + `api` + `prometheus` + `grafana` 一键 `up`；宿主机只 `curl` |
| **怎么区分** | 前期练习常「Compose 只起 Postgres，API 本机 uvicorn」——那是依赖进容器，**不算**整栈部署验收 |

### 服务名 DNS 与端口映射

| 层 | 说明 |
|----|------|
| **是什么** | Compose 网络里用**服务名**当主机名；`ports: "5434:5432"` 左边是宿主机口、右边是容器口 |
| **在本文干什么** | API 环境变量：`postgresql://cs:cs@postgres:5432/...` |
| **怎么区分** | 宿主机连库用 `127.0.0.1:5434`；容器互连**不要**写映射口 5434，也不要写 `127.0.0.1`（那是容器自己） |

### Prometheus `/metrics` 与 QPS

| 层 | 说明 |
|----|------|
| **是什么** | 应用露出累计计数、直方图等**原料**；采集端再算吞吐 |
| **在本文干什么** | `Instrumentator` 挂上 `/metrics`；Grafana 用 `rate(http_requests_total[1m])` 近似 QPS |
| **怎么区分** | `/metrics` 里通常没有一行叫 `QPS=12`；Counter 是里程表，QPS 是车速（rate） |

### Grafana 大盘 vs 单次 Trace / 请求日志

| 层 | 说明 |
|----|------|
| **是什么** | 大盘看一段时间整体；Trace/日志看这一枪细节 |
| **在本文干什么** | Grafana：QPS / P99 / 错误率；中间件打印 `request_id` + `duration_ms`，响应头带回 `X-Request-ID` |
| **怎么区分** | 先看面确认「是否真慢」，再用 ID 对上某次请求。本 API 暂无 LLM，故用日志作**等价**链路；有模型调用时可再挂 LangSmith |

### Locust、QPS、P99

| 层 | 说明 |
|----|------|
| **是什么** | Locust 模拟多用户打接口；报告里 Requests/s ≈ QPS，99% ≈ P99 |
| **在本文干什么** | 对 `POST /ask` 加压，对照门槛 QPS>200 且 P99<500ms |
| **怎么区分** | Max 是极端尖峰；门槛看的是 **P99**。达不到也要有参数与数字报告，不能假装没测 |

```text
宿主机 curl / Locust
        │
        ▼
   api:8048 ←→ postgres（服务名，5432）
        │
        ▼ /metrics
   prometheus ──► grafana（大盘）
        │
   docker logs：request_id + duration_ms（单次）
```

---

## 环境准备

- Docker Desktop  
- 本机 Python ≥3.12 + [uv](https://github.com/astral-sh/uv)（压测用）  
- 端口示例：API `8048`，Prometheus `19048`，Grafana `13048`，Postgres 宿主机 `5434`（避开已被占用的 `5433`）

---

## 动手：整栈 Compose

目录要点：`Dockerfile` 打 API 镜像；`docker-compose.yml` 含四服务；`DATABASE_URL` 指向 `postgres:5432`。

```bash
cd week07/day48-51-customer-service-optimize   # 或你的练习目录
docker compose up -d --build

curl -s http://127.0.0.1:8048/ask -H 'Content-Type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？"}'
```

期望：`source` 为 `db`，含状态与物流单号。

**新手坑**：`Bind ... 5433 failed: port is already allocated`  
→ 宿主机映射口被别的容器占用。改左边端口（如 `5434:5432`）即可；**不要**改容器内 `DATABASE_URL` 的 `5432`。

---

## 动手：Prometheus 原料

在 FastAPI 里（`app = FastAPI(...)` 之后）：

```python
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

依赖写入 `requirements.txt` 后重建镜像。验证：

```bash
curl -s http://127.0.0.1:8048/ask -H 'Content-Type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？"}' > /dev/null
curl -s http://127.0.0.1:8048/metrics | rg 'http_requests_total'
```

期望能看到带 `handler="/ask"` 的 Counter 行。

---

## 动手：Grafana 大盘 + 单次日志

Compose 内 Prometheus 刮 `api:8000/metrics`（同网用服务名，不是宿主机 8048）。

- Targets：http://127.0.0.1:19048/targets → `day48-cs` 应为 **UP**  
- Grafana：http://127.0.0.1:13048 （默认 `admin` / `admin`）→ 大盘含 QPS / P99 / 错误率  

单次等价 Trace（中间件示意）：

```python
# 每个请求打印一行，并写回 X-Request-ID
print(f"trace request_id={rid} path={path} status={code} duration_ms={ms}")
```

```bash
curl -s -D - http://127.0.0.1:8048/ask \
  -H 'Content-Type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？"}' -o /tmp/ask.json
docker compose logs api --tail 30
```

用响应头里的 `x-request-id` 对上日志里的 `request_id=`。

---

## 动手：Locust 压测

```bash
uv sync
uv run locust -f locustfile.py --host http://127.0.0.1:8048 \
  --headless -u 50 -r 10 -t 30s
```

读末尾：**Requests/s**、**99%**、**Fails**。  
示例结论（本机一次实测）：约 **281 req/s**，**99%=250ms**，失败 0 → 对照「QPS>200 且 P99<500ms」**达标**（参数：50 用户 / 30s / 库路径 ORD-1001）。换更重负载或 FAQ 路径，数字可能变化，报告里写清参数。

---

## 项目文档最少四块

外人打开 README 应能独立：

1. **起栈** — `docker compose up -d --build`  
2. **调 API** — curl `/ask` 的库路径与 FAQ 路径  
3. **压测** — Locust 命令 + 怎么读 QPS/P99 + 一次实测数字  
4. **看监控** — `/metrics`、Prometheus targets、Grafana 入口  

缺压测或监控入口 = 文档不及格。

---

## 边界（故意没做）

- FAQ 升级为向量 / 混合检索 + LLM 生成（可选加深，不替代压测与部署）  
- 真 LangSmith 调用树：等接入模型后再挂环境变量；本文用请求日志作等价 Trace  
- 项目二投研 Multi-Agent（后续天数）  

---

## 收工

```bash
docker compose down
```

你现在有的是：可一键起的客服栈、可刮取的指标、可看的大盘、可对上的单次请求 ID、一份带数字的压测结论，以及能让外人照做的文档——这才是「优化与部署」阶段要交的东西。
