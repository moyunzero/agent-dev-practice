# 安装 Grafana 并做一个简单大盘：把 Day30 的 Prometheus 指标画出来

Day30 已经让 FastAPI 通过 `/metrics` 吐出了 QPS、延迟、错误率的原料，以及缓存 hit/miss。  
下一步不是再写业务代码，而是回答：

> 过去 15 分钟请求速率怎样？延迟和错误有没有毛刺？缓存命中在涨吗？

**Grafana** 负责把时间序列画成大盘；**Prometheus** 负责刮取并保存历史。本文用 Docker Compose 一键安装两者，刮取本机 FastAPI 的 `/metrics`，并给出一个含 4 个面板的简单 Dashboard。

## 你将会得到什么

1. 分清 **`/metrics` → Prometheus → Grafana** 的数据流  
2. 用 Compose **安装 Grafana**（及配套 Prometheus），避开常见端口冲突  
3. 在 Grafana Explore 验证能查到指标，再打开预置 **Dashboard**  
4. 能指着面板讲清：QPS≈`rate(Counter)`、延迟来自 Histogram、错误率是比值、缓存是自定义 Counter  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### `/metrics`（应用暴露端点）

| 层 | 说明 |
|----|------|
| **是什么** | 应用进程返回的 Prometheus **文本快照**：当前 Counter / Histogram 的值 |
| **在本文干什么** | FastAPI（Day30 同款）在 `:8030/metrics` 吐数；Prometheus 来刮 |
| **怎么区分** | 快照 ≠ 历史。只 curl `/metrics` 看不到「15 分钟趋势」；趋势要靠 Prometheus 存时间序列 |

### Prometheus（刮取与存储）

| 层 | 说明 |
|----|------|
| **是什么** | 按配置定期 **scrape** 各 `/metrics`，存成时间序列，支持 **PromQL** 查询 |
| **在本文干什么** | Compose 里跑一个 Server；`prometheus.yml` 指向宿主机 API |
| **怎么区分** | 它**存历史**；Grafana 一般**不存**业务指标历史，只是问它要数 |

### Grafana（可视化）

| 层 | 说明 |
|----|------|
| **是什么** | 监控大盘 UI：接 Data source，用 Panel 画折线/数字等 |
| **在本文干什么** | 安装（Compose）+ 打开预置 Dashboard「Day31 · Day30 FastAPI」 |
| **怎么区分** | 装了 Grafana ≠ 自带 QPS。没有 Prometheus（或其它源）+ 应用暴露，大盘是空的 |

### Data source

| 层 | 说明 |
|----|------|
| **是什么** | Grafana 里「去哪取数」的连接（本文：Prometheus `http://prometheus:9090`） |
| **在本文干什么** | 用 provisioning 自动配好，免手工点 |
| **怎么区分** | 不配 Data source → PromQL 无处执行 → Panel 无数据 |

### Dashboard 与 Panel

| 层 | 说明 |
|----|------|
| **是什么** | **Dashboard** = 一整页大盘；**Panel** = 上面一块图 |
| **在本文干什么** | 一页 4 个 Panel：请求速率、平均延迟、错误率、缓存 hit/miss |
| **怎么区分** | Explore = 临时查数；Dashboard = 固化下来的多图一页 |

### PromQL 与 `rate()`

| 层 | 说明 |
|----|------|
| **是什么** | Prometheus 查询语言。`rate(counter[1m])` ≈ 近 1 分钟 Counter 的每秒增速 |
| **在本文干什么** | QPS 面板用 `rate(http_requests_total[…])`；不要直接把累计值当 QPS |
| **怎么区分** | Counter 绝对值只增；**速率**才是吞吐直觉 |

### `host.docker.internal`

| 层 | 说明 |
|----|------|
| **是什么** | Docker Desktop 提供的特殊主机名：从**容器内**访问**宿主机**网络 |
| **在本文干什么** | Prometheus 容器 scrape `host.docker.internal:8030` |
| **怎么区分** | 容器内 `127.0.0.1` = 容器自己，**不是**你的笔记本。API 在宿主机时必须用 host.docker.internal（或等价方案） |

```text
宿主机 FastAPI :8030/metrics
        ▲ scrape（每 5s）
Prometheus 容器（对外映射如 :19090）
        ▲ Data source
Grafana 容器（对外映射如 :13031）
  └── Dashboard → Panel × N
```

---

## 要解决什么问题

| 只有 curl `/metrics` | 加上 Grafana 大盘 |
|----------------------|-------------------|
| 看到当前累计值 | 看到 **15 分钟趋势** |
| 难同时盯 QPS/延迟/错误/缓存 | 一页四图对照 |
| 端口被其它项目占用时懵 | 本文用 **19090 / 13031**，避开常见 9090/3000 |

---

## 环境准备（从零开始）

需要：

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（或等价 Docker Engine + Compose）  
- Python 3.11+ 与 [uv](https://docs.astral.sh/uv/)，用于跑带 `/metrics` 的 FastAPI  
- 空出端口：**19090**（Prometheus）、**13031**（Grafana）、**8030**（API）  

若本机已有其它 Prometheus（常见占用 `9090`），不要硬抢——改映射端口即可（本文已示范）。

---

## 完整代码

### 1. FastAPI + `/metrics`（与 Day30 同构，最小版）

`app/main_api.py`：

```python
from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="metrics-demo")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

CACHE_LOOKUPS = Counter(
    "cache_lookups_total",
    "Ask answer cache lookups",
    labelnames=("result",),
)
_ANSWER_CACHE: dict[str, str] = {}


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

依赖：`fastapi`、`uvicorn[standard]`、`prometheus-fastapi-instrumentator`。

```bash
uv run uvicorn main_api:app --port 8030
```

### 2. `prometheus.yml`

```yaml
global:
  scrape_interval: 5s

scrape_configs:
  - job_name: day30-fastapi
    metrics_path: /metrics
    static_configs:
      - targets: ["host.docker.internal:8030"]
        labels:
          service: day30-prometheus
```

### 3. `docker-compose.yml`

```yaml
services:
  prometheus:
    image: prom/prometheus:v2.54.1
    ports:
      - "19090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"

  grafana:
    image: grafana/grafana:11.2.0
    ports:
      - "13031:3000"
    environment:
      GF_SECURITY_ADMIN_USER: admin
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_USERS_ALLOW_SIGN_UP: "false"
    volumes:
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
    depends_on:
      - prometheus
```

### 4. Grafana Data source 预置

`grafana/provisioning/datasources/prometheus.yml`：

```yaml
apiVersion: 1

datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: true
```

Dashboard JSON 可放在 `grafana/provisioning/dashboards/json/`，由 provider 自动加载（面板含 QPS / 延迟 / 错误率 / 缓存）。官方入门：[Grafana getting started](https://grafana.com/docs/grafana/latest/getting-started/)。

---

## 这段配置在干什么

| 片段 | 作用 |
|------|------|
| `targets: host.docker.internal:8030` | 容器内 Prometheus 刮宿主机 API |
| `19090:9090` / `13031:3000` | 宿主机访问入口；避开常见占用 |
| Data source `url: http://prometheus:9090` | **容器网内** Grafana 找 Prometheus（用服务名，不是 19090） |
| Dashboard Panels | 用 PromQL 把 Day30 指标画成趋势 |

注意两套地址：

- 你在浏览器打开：`localhost:19090`、`localhost:13031`  
- Grafana 容器访问 Prometheus：`http://prometheus:9090`（Compose 服务名）

---

## 启动与验证

**终端 A — API：**

```bash
uv run uvicorn main_api:app --port 8030
curl -s http://127.0.0.1:8030/metrics | head
```

**终端 B — 监控栈：**

```bash
docker compose up -d
docker compose ps
```

**验收清单（对照实拍）：**

### 1）Prometheus targets 为 UP

打开 http://127.0.0.1:19090/targets ，应看到 job **`day30-fastapi`**，endpoint 为 `host.docker.internal:8030/metrics`，状态 **UP**：

![Prometheus targets：day30-fastapi UP](./assets/day31/01-prometheus-targets-up.png)

若这里是别的项目的 job（如 `agent-service`），说明你打开了**另一套** Prometheus（常见占用 `:9090`），请改用本文的 **`:19090`**。

### 2）Grafana Explore 能查到序列

http://127.0.0.1:13031 → `admin` / `admin` → **Explore** → Data source 选 **Prometheus** → Metric 选 `http_requests_total` → Run query。应出现带 `job="day30-fastapi"` 的折线：

![Grafana Explore：http_requests_total](./assets/day31/02-grafana-explore-http-requests.png)

这是「不建 Dashboard 也能确认取数成功」的最短路径。

### 3）打开简单监控大盘

**Dashboards** → **Day31 · Day30 FastAPI**（或 http://127.0.0.1:13031/d/day31-day30-fastapi ）。打点流量后 Refresh：

```bash
curl -s 'http://127.0.0.1:8030/ask?q=hello'
curl -s 'http://127.0.0.1:8030/ask?q=hello'
curl -s http://127.0.0.1:8030/fail
```

实拍四面板（Request rate / Avg latency / Error rate / Cache lookups）：

![Grafana Dashboard：四面板](./assets/day31/03-grafana-dashboard-four-panels.png)

**面板怎么读：**

| 面板 | 读法 |
|------|------|
| Request rate | `rate(http_requests_total[1m])` ≈ QPS |
| Avg latency | Histogram sum/count 的比率 ≈ 平均延迟 |
| Error rate | `rate(5xx) / rate(all)` |
| Cache lookups | `cache_lookups_total` 的 hit / miss 累计曲线 |

---

## 踩过的坑

### 1. `Bind for 9090 failed: port is already allocated`

**现象**：Compose 起不来。  
**原因**：本机已有其它 Prometheus（或其它服务）占 9090。  
**处理**：改宿主机映射（如 `19090:9090`），浏览器改开新端口；**不要**和别的项目的 targets 页搞混。

### 2. targets DOWN / Explore No data

**现象**：Grafana 空白。  
**先查**：① API 是否在 `:8030`；② `/targets` 是否 UP；③ Explore 是否选了 Prometheus 且选了 metric、时间范围够近。

### 3. 容器里写 `127.0.0.1:8030`

**现象**：永远 scrape 失败。  
**原因**：127.0.0.1 在容器内指自己。  
**处理**：`host.docker.internal:8030`（并保留 `extra_hosts: host-gateway`）。

### 4. Explore 已通，Dashboard 仍空

**现象**：临时查询有数，大盘没有。  
**处理**：确认 Panel 的 Data source、PromQL、时间范围；预置看板 uid 是否加载成功（重启 Grafana 容器）。

---

## 取舍与未做之事

| 做了 | 故意没做 |
|------|----------|
| Compose 安装 Grafana + Prometheus | 告警规则、PagerDuty |
| 预置 Data source + 简单 4 Panel 大盘 | 漂亮的生产级 Dashboard 模板市场深挖 |
| 刮取本机 FastAPI `/metrics` | ELK、完整业务 Compose（后续主题） |
| 端口避开占用 | 强制停掉读者机器上其它项目的监控栈 |

---

## 小结

- **数据流**：应用 `/metrics` → Prometheus 刮取存历史 → Grafana Data source → Dashboard/Panel。  
- **安装 Grafana** 用 Compose 即可；大盘展示的是 Prometheus 里已有的 Day30 指标。  
- **QPS** 看 `rate(Counter)`；缓存 hit/miss 是业务自定义 Counter，Grafana 只负责画。  
- 验收口令：targets **UP** + Explore 有曲线 + 大盘至少两块能讲清。  

下一步常见是把 FastAPI 与依赖服务一并 **Docker / Compose** 编排——监控栈已经就位，业务栈可以收进同一张编排图。

---

*系列笔记 · Agent 工程跟练 · Week 5 Day 31*
