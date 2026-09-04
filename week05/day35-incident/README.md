# Week 5 / Day 35 — 生产故障模拟与工具链定位

> **状态**：`available`  
> **长文教程**（可选）：[模拟一次线上故障：用可观测工具链定位问题](../../notes/week05/day35-incident.md)

## 今日目标

模拟一次线上故障，并使用本周学习的工具链进行问题定位。  
加码：最小 Elasticsearch + Kibana，按字段检索 JSON 日志。

## 前置

- Python 3.11+、uv  
- Docker Desktop（ES + Kibana；内存建议 ≥2GB）  
- 端口：**8035**（API）、**19200**（ES）、**15601**（Kibana）

## 文件说明

| 文件 | 作用 |
|------|------|
| `lesson01_incident_map.md` … `lesson05_week_map.md` | 课内讲义 |
| `main_api.py` | 故障 API（`FAULT=off\|slow\|error`） |
| `docker-compose.yml` | ES + Kibana |
| `seed_to_es.py` | 样例 JSON 写入 ES |
| `pyproject.toml` / `uv.lock` | 依赖 |

## 推荐顺序

| 步骤 | 命令 / 动作 | 说明 |
|:----:|-------------|------|
| 1 | 读 lesson01 | 面 → 点 → 路径 |
| 2 | `FAULT=… uv run uvicorn main_api:app --port 8035` | 复现慢 / 5xx |
| 3 | 对照 JSON 字段 | `duration_ms` vs `status` |
| 4 | `docker compose up -d` → `seed_to_es.py` → Kibana | `status:500` / `fault:slow` |

## 验收命令（汇总）

```bash
cd week05/day35-incident
uv sync

FAULT=slow uv run uvicorn main_api:app --port 8035
# 另开终端：
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=b'

docker compose up -d
uv run python seed_to_es.py
# 浏览器 http://127.0.0.1:15601 → Data View day35-logs* → Discover 过滤 status:500

docker compose down
```

**期望**：slow 时 time≈2s 且日志 `duration_ms` 大；error 时 HTTP 500；Kibana 能按字段命中样例。
