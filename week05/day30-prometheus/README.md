# Week 5 / Day 30 — Prometheus 指标监控

> **状态**：`available`  
> **长文教程**（可选）：[用 Prometheus 暴露 FastAPI 的 QPS、延迟与错误率](../../notes/week05/day30-prometheus.md)

## 今日目标

暴露 API 的 **QPS、延迟、错误率** 等核心指标；并加至少一个业务自定义指标（缓存命中）。

## 前置

- Python 3.11+、uv  
- 无需 Grafana / 无需本机 Prometheus Server（curl `/metrics` 即可验收）

## 文件说明

| 文件 | 作用 |
|------|------|
| `main_api.py` | FastAPI + Instrumentator + `cache_lookups_total` |
| `lesson01_metrics_map.md` | Counter / Histogram / Gauge 对照 |
| `pyproject.toml` / `uv.lock` | 依赖锁定 |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 1 | 读 `lesson01_metrics_map.md` | 三类指标与 QPS/延迟/错误率 |
| 2 | `uv sync` + `uvicorn main_api:app --port 8030` | 起服务 |
| 3 | curl `/ask`、`/fail`、`/metrics` | 核验 HTTP 指标 |
| 4 | 同 `q` 打两次 `/ask` | 看 `cache_lookups` hit/miss |

## 验收命令（汇总）

```bash
cd week05/day30-prometheus
uv sync
uv run uvicorn main_api:app --port 8030
```

另开终端：

```bash
curl -s 'http://127.0.0.1:8030/ask?q=hello'
curl -s 'http://127.0.0.1:8030/ask?q=hello'
curl -s http://127.0.0.1:8030/fail
curl -s http://127.0.0.1:8030/metrics | rg 'http_requests_total|http_request_duration|cache_lookups'
```

**期望**：见 `http_requests_total`（含 2xx/5xx）、duration histogram、以及 `cache_lookups_total` 的 hit/miss。
