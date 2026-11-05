# Day35 Lesson 3 — 用工具链信号钉死故障

> 挂钩上游：**使用本周学习的工具链进行问题定位**  
> 本课：对着真实 JSON 行做「现象 → 信号 → 结论」。ES/Kibana 留到第 4 课。

## 排障决策树（本日最小版）

```text
用户喊：接口不对劲
        │
        ├─ 还活着吗？ → curl /health（Docker 课同理：ps / health）
        │
        ├─ 整体怎样？ →（生产）Metrics/Grafana 延迟与 5xx
        │              （本课桌面）看 curl time_total + 多打几枪是否稳定复现
        │
        └─ 这一枪怎样？ → uvicorn 上的 JSON：
               status / duration_ms / fault / path / request_id
```

## 三种故障在日志里长什么样

| FAULT | HTTP | 日志里关键字段 | 人话结论 |
|-------|------|----------------|----------|
| `off` | 200 | `duration_ms` 很小，`fault=off` | 正常 |
| `slow` | 200 | **`duration_ms` 很大**，`fault=slow` | 成功但慢（依赖拖死一类） |
| `error` | 500 | **`status=500`**，`fault=error`，`duration_ms` 通常不大 | 直接失败 |

**易混**：慢 ≠ 一定 5xx。只看状态码会漏掉 `slow`。

## 和本周其它工具怎么接力（口述用）

| 若还要更深 | 用 |
|------------|-----|
| Agent 多步里哪一环慢 | Day29 Trace |
| 线上从哪分钟开始飙 | Day31 Grafana |
| 海量日志按 `status=500` 搜 | 第 4 课 ES+Kibana |

本课脚本仍是 `main_api.py`（第 2 课已带读），不新增文件。

## 动手（对照三枪）

保持 API 在 `:8035`。每换一次 `FAULT` 都要**重启**。

```bash
# 1) 正常
FAULT=off uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=a'
# 盯 uvicorn：记下 duration_ms / status / fault

# 2) 慢
FAULT=slow uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=b'

# 3) 错
FAULT=error uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=c'
```

**观察任务**：用一句话描述「slow 与 error 在 JSON 上差在哪两个字段」。
