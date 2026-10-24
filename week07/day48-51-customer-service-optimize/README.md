# Week 7 / Day 48–51 — 项目一：优化与部署

> **状态**：`available`  
> **长文教程**：[智能客服优化与部署：Compose 整栈、监控大盘与压测达标](../../notes/week07/day48-51-customer-service-optimize.md)

## 今日目标

完成性能优化、监控集成和 Docker 部署，撰写项目文档：Compose 整栈（API + Postgres + Prometheus + Grafana）、Locust 压测读 QPS/P99、可对外复现的 README。

## 前置

- Docker Desktop  
- 本机 Python ≥3.12 + uv（压测）  
- 端口：API `8048`、Prometheus `19048`、Grafana `13048`、Postgres 宿主机 `5434`（避让占用）

## 文件说明

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | postgres + api + prometheus + grafana |
| `Dockerfile` / `app_main.py` / `faq_search.py` / `faq/` | 客服 API 镜像与业务 |
| `prometheus.yml` / `grafana/` | 刮取与预置大盘 |
| `locustfile.py` / `pyproject.toml` | Locust 压测 |
| `data/seed.sql` | Postgres 种子数据 |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | `docker compose up -d --build` | 整栈起 |
| 2 | curl `POST /ask`（库 + FAQ） | 验业务 |
| 3 | curl `/metrics`；打开 targets / Grafana | 验监控 |
| 4 | `uv run locust ... --headless` | 读 QPS / P99 |
| 5 | `docker compose down` | 收工 |

## 验收命令（汇总）

```bash
cd week07/day48-51-customer-service-optimize
docker compose up -d --build

curl -s http://127.0.0.1:8048/ask -H 'Content-Type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？"}'
curl -s http://127.0.0.1:8048/ask -H 'Content-Type: application/json' \
  -d '{"q":"七天无理由退货吗？"}'

curl -s http://127.0.0.1:8048/metrics | rg 'http_requests_total' | head
# 浏览器：http://127.0.0.1:19048/targets （day48-cs UP）
# 浏览器：http://127.0.0.1:13048 （admin/admin）大盘 Day48 · Customer Service API

uv sync
uv run locust -f locustfile.py --host http://127.0.0.1:8048 \
  --headless -u 50 -r 10 -t 30s

docker compose down
```

**期望**：`source` 为 `db` / `faq`；targets UP；Locust 可读出 Requests/s 与 99%，并对照 QPS>200、P99<500ms 写结论。
