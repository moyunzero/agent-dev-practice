# Day35 Lesson 2 — 故障注入 API（带读再跑）

> 挂钩上游：**模拟一次线上故障**  
> 本课只做到：能复现慢请求 / 5xx；定位信号留到第 3 课。

## 故障开关（环境变量 `FAULT`）

| 值 | 行为 |
|----|------|
| `off`（默认） | `/ask` 正常 echo |
| `slow` | `/ask` 先 `sleep` 再返回（模拟依赖拖慢） |
| `error` | `/ask` 直接 **500**（模拟下游炸了） |

改故障：**改环境变量后重启** uvicorn（本课不做热切换，避免魔法）。

## 主流程（`main_api.py`）

```text
请求进入
  → RequestJsonLogMiddleware（终于记 JSON：path/status/duration_ms/…）
  → /ask 读 FAULT
       off   → 200 + echo
       slow  → sleep → 200（但 duration_ms 很大）
       error → 抛 HTTP 500
```

点读：

1. `FAULT = os.getenv("FAULT", "off")` — 故障从哪来  
2. `ask()` 里 `if FAULT == "slow"` / `"error"` — 注入点  
3. 中间件 `finally` 里 `log.info("request_done", …)` — 无论成败都打一行 JSON（来源：Day34 模式）

## 动手（只跑本课）

```bash
cd week05/day35-incident
uv sync

# 终端 A：正常
FAULT=off uv run uvicorn main_api:app --port 8035

# 另开终端 B：
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=ok'

# 停掉 A，再起慢故障：
FAULT=slow uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=slow'

# 再换成 5xx：
FAULT=error uv run uvicorn main_api:app --port 8035
curl -s -w '\nHTTP %{http_code} time=%{time_total}\n' 'http://127.0.0.1:8035/ask?q=boom'
```

**观察**：uvicorn 终端里的 JSON — `status`、`duration_ms`、`fault` 字段随模式变化。
