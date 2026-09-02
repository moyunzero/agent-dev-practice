# Week 4 / Day 28 — Locust + JMeter 压测

> **状态**：`available`  
> **长文教程**（可选）：[用 Locust 和 JMeter 压测：读懂 QPS、P99](../../notes/week04/day28-load-test.md)

## 今日目标

对 Day24–25 异步 API 压测；Locust + JMeter 读 RPS/Throughput、P99；对比 `/async-ask` vs `/async-block`。

## 前置

- 被测服务：`../day24-25-async/main_api.py` 端口 **8024**
- Java 11+（JMeter）；Locust 由本目录 `uv sync` 提供

## 文件说明

| 文件 | 作用 |
|------|------|
| `locustfile_async_ask.py` | Locust：打 `/async-ask`（优化路径） |
| `locustfile_async_block.py` | Locust：打 `/async-block`（反例路径） |
| `jmeter_async_ask.jmx` | JMeter 计划：async-ask |
| `jmeter_async_block.jmx` | JMeter 计划：async-block |
| `pyproject.toml` / `uv.lock` | locust |
| `.tools/apache-jmeter-*` | 可选本地 JMeter（gitignore，需自行解压） |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 0 | 终端 A：Day24–25 起 uvicorn :8024 | 被测 API |
| 1 | 本目录 `uv sync` | Locust |
| 2 | `locust -f locustfile_async_ask.py` | 浏览器 :8089 设用户数 |
| 3 | 记录 RPS、99%ile |
| 4 | 换 `locustfile_async_block.py` | 对照更差指标 |
| 5 | （可选）JMeter CLI 跑 `.jmx` | 读 Throughput、99th |

## 验收命令（汇总）

**终端 A — 被测服务：**

```bash
cd ../day24-25-async
uv sync
uv run uvicorn main_api:app --port 8024
```

**终端 B — Locust：**

```bash
cd ../day28-load-test
uv sync
uv run locust -f locustfile_async_ask.py --host http://127.0.0.1:8024
# 浏览器 http://127.0.0.1:8089
# 对照：locustfile_async_block.py
```

**JMeter（非 GUI，需本地 JMeter）：**

```bash
JMETER=./.tools/apache-jmeter-5.6.3/bin/jmeter
"$JMETER" -n -t jmeter_async_ask.jmx -l results_async_ask.jtl -e -o jmeter-out
```

## 验收标准

- ask 路径 QPS/RPS 明显高于 block
- 能指出 Locust 的 99%ile ≈ P99；JMeter 的 Throughput ≈ QPS

## 收工清理

```bash
# 停 uvicorn / Locust
rm -rf .venv __pycache__ jmeter-out jmeter-out-block *.jtl jmeter.log
```
