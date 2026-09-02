# Week 3 / Day 16 — 自定义天气工具

> **状态**：`available`  
> **长文教程**（可选）：[手写查天气自定义工具并挂进 LangChain Agent](../../notes/week03/day16-custom-weather-tool.md)

## 今日目标

手写 Open-Meteo 真实 HTTP 查天气 `@tool`；单测工具；挂进 `create_agent`。

## 前置

- Day 15 Agent 基础
- 外网（Open-Meteo 免 Key）；无网时 `WEATHER_FAKE=1` 兜底（非主验收）

## 文件说明

| 文件 | 作用 |
|------|------|
| `step01_weather_tool.py` | **第 1 步**：仅测 `@tool` invoke，不经过 Agent |
| `demo_weather_agent.py` | **第 2 步**：Agent + 天气工具；CLI 传入城市问句 |
| `pyproject.toml` / `uv.lock` | httpx、langchain |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_weather_tool.py` | 真实气温 + `来源：Open-Meteo` |
| 2 | `demo_weather_agent.py "杭州天气怎么样？"` | 轨迹含 `get_weather` + 自然语言回答 |

## 验收命令（汇总）

```bash
cd week03/day16-custom-weather-tool
uv sync
uv run python step01_weather_tool.py
uv run python demo_weather_agent.py "杭州天气怎么样？"
```

## 验收标准

- Observation 含真实气温与 `来源：Open-Meteo`
- Agent 轨迹有 `Action: get_weather`

## 收工清理

```bash
rm -rf .venv __pycache__
```
