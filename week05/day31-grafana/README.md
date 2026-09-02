# Week 5 / Day 31 — Grafana 可视化

> **状态**：`available`  
> **长文教程**（可选）：[安装 Grafana 并做一个简单大盘](../../notes/week05/day31-grafana.md)

## 今日目标

安装 Grafana，创建简单监控大盘，展示 Day30 Prometheus 指标（QPS / 延迟 / 错误率 + 缓存）。

## 前置

- Docker Desktop  
- Day30 API：`../day30-prometheus` 端口 **8030**  
- 本课端口：**19090**（Prometheus）、**13031**（Grafana），避开常见 9090/3000 占用

## 文件说明

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | Prometheus + Grafana |
| `prometheus.yml` | scrape `host.docker.internal:8030/metrics` |
| `grafana/provisioning/` | Data source + Dashboard 预置 |
| `lesson01_grafana_map.md` | 组件地图 |

## 推荐顺序

| 步骤 | 命令 / 操作 | 说明 |
|:----:|-------------|------|
| 0 | Day30：`uv run uvicorn main_api:app --port 8030` | 先起 API |
| 1 | 本目录 `docker compose up -d` | 起监控栈 |
| 2 | 打开 :19090/targets | `day30-fastapi` = UP |
| 3 | 打开 :13031 Explore | 查 `http_requests_total` |
| 4 | Dashboard「Day31 · Day30 FastAPI」 | 四块面板 |

## 验收命令（汇总）

```bash
# 终端 A
cd week05/day30-prometheus && uv sync && uv run uvicorn main_api:app --port 8030

# 终端 B
cd week05/day31-grafana
docker compose up -d
docker compose ps
```

浏览器：

- http://127.0.0.1:19090/targets  
- http://127.0.0.1:13031 （admin / admin）  
- Dashboard：http://127.0.0.1:13031/d/day31-day30-fastapi  

实拍对照（文章内嵌）：`notes/week05/assets/day31/` — targets UP / Explore / 四面板大盘。

**期望**：targets UP；Explore 有序列；大盘可见 Request rate / latency / error / cache。

收工：`docker compose down`；停掉 Day30 uvicorn。
