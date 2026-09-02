# Week 4 / Day 28 — Locust + JMeter 压测

> **状态**：`available`
> 对外文章：[用 Locust 和 JMeter 压测：读懂 QPS、P99，并对比优化前后](../../notes/week04/day28-load-test.md)

## 前置

- 被测 API：Day24–25 `main_api.py`（端口 **8024**），或按对外文章自备同款路由  
- Java 11+（JMeter）；本目录 `.tools/apache-jmeter-5.6.3/` 可回看时复用  

## 验收命令

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
# 浏览器 http://127.0.0.1:8089 ；对照用 locustfile_async_block.py
```

**JMeter（非 GUI）：**

```bash
JMETER=./.tools/apache-jmeter-5.6.3/bin/jmeter
"$JMETER" -n -t jmeter_async_ask.jmx -l results_async_ask.jtl -e -o jmeter-out
# 对照：jmeter_async_block.jmx
```

**期望**：ask 吞吐明显高于 block；能指出 QPS/RPS（Throughput）与 P99（99%ile / 99th）。

## 收工清理

```bash
# 停 uvicorn / Locust
rm -rf .venv __pycache__ jmeter-out jmeter-out-block *.jtl jmeter.log
# .tools/ 按需保留
```
