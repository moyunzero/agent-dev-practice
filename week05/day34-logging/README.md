# Week 5 / Day 34 — JSON 结构化日志

> **状态**：`available`  
> **长文教程**（可选）：[把 FastAPI 日志打成 JSON](../../notes/week05/day34-logging.md)

## 今日目标

配置应用将日志输出为 JSON 格式，为接入 ELK 做准备。

## 前置

- Python 3.11+、uv  
- 端口 **8034**（本课 API）

## 文件说明

| 文件 | 作用 |
|------|------|
| `step02_json_logger.py` | 最小 JSON 日志示例 |
| `main_api.py` | FastAPI + 请求中间件打 JSON |
| `lesson01_json_log_map.md` 等 | 课内讲义 |
| `pyproject.toml` / `uv.lock` | 依赖 |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 1 | 读 lesson01 | JSON vs print、ELK |
| 2 | `uv run python step02_json_logger.py` | 见 JSON 行 |
| 3 | `uv run uvicorn main_api:app --port 8034` | 起 API |
| 4 | curl `/ask`，看 uvicorn 终端 | 验收 |

## 验收命令（汇总）

```bash
cd week05/day34-logging
uv sync
uv run python step02_json_logger.py

uv run uvicorn main_api:app --port 8034
# 另开终端：
curl -s 'http://127.0.0.1:8034/ask?q=hello'
```

**期望**：uvicorn 终端出现含 `event`/`path`/`status`/`duration_ms` 的 JSON 行。
