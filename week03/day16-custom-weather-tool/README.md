# Week 3 / Day 16 — 自定义天气工具

> **状态**：`available`
> 对外文章：[手写查天气自定义工具（真实 API），并挂进 LangChain Agent](../../notes/week03/day16-custom-weather-tool.md)

## 前置

- 能访问外网（默认 [Open-Meteo](https://open-meteo.com/)，**免 API Key**）  
- 第 2 课需要 Ollama（默认 `qwen2:7b`）  
- 无网时：`WEATHER_FAKE=1` 用本地字典兜底（不替代主路径）

## 验收命令（全文）

```bash
cd week03/day16-custom-weather-tool

uv sync
uv run python step01_weather_tool.py
uv run python demo_weather_agent.py "杭州天气怎么样？"
```

**期望**：结果含真实气温与 `来源：Open-Meteo`；Agent 轨迹有 `Action: get_weather`。

## 脚本

| 脚本 | 用途 |
|------|------|
| `step01_weather_tool.py` | Open-Meteo HTTP + `@tool` 单测 |
| `demo_weather_agent.py` | `create_agent` 集成 |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
```
