# 手写查天气自定义工具（真实 API），并挂进 LangChain Agent

Day15 已经会用 `@tool` 做加减——机制通了。上游 Day16 的目标是：**编写一个查询天气的自定义工具，并集成到 Agent 中**。  
「查询」意味着工具函数要向外部气象服务要数据，而不是只读本地假字典。本文用免费、免注册的 [Open-Meteo](https://open-meteo.com/)：城市名 → 经纬度 → 当前气温，再用 `create_agent` 挂进 Agent。无网时可用 `WEATHER_FAKE=1` 兜底，**不替代**真实查询主路径。

## 你将会得到什么

1. 写出带 HTTP 的 `get_weather`（地理编码 + 预报）并用 `@tool` 暴露  
2. 先 `invoke` 单测真实返回，再挂进 Agent  
3. 问「杭州天气」时轨迹出现 `get_weather`，Observation 含真实气温与来源标注  
4. 分清：假数据只是兜底；MCP 本日只知边界  

---

## 零基础名词表

> 建议先读完本节再动手。

### 自定义工具（Custom Tool）

| 层 | 说明 |
|----|------|
| **是什么** | 你自己写函数逻辑，再用 `@tool` 做成 Agent 可调用的工具 |
| **在本文干什么** | `get_weather(city)` 发 HTTP 查天气，返回给人/模型读的字符串 |
| **怎么区分** | 与 Day15 `add` **机制相同**；Day16 函数体多了**访问外部服务**（网络请求），这才叫「查询天气」 |

```text
用户问「杭州天气？」
  → 模型 Action: get_weather(city=杭州)
  → 你的函数: 地理编码 API → 预报 API
  → Observation: 「杭州：…，气温 27.9°C（来源：Open-Meteo）」
  → 模型写 Answer
```

### HTTP API / Open-Meteo

| 层 | 说明 |
|----|------|
| **是什么** | 通过网址发请求、拿回 JSON 数据的服务。Open-Meteo 提供天气预报，**不需 API Key** |
| **在本文干什么** | 两步：① `geocoding-api` 把「杭州」变成经纬度 ② `forecast` 取当前 `temperature_2m` 与 `weather_code` |
| **怎么区分** | 假字典：写死在代码里，永远 22°C。真 API：随真实天气变，需要外网；失败时工具应返回**可读错误字符串**，方便 Observation 暴露问题 |

### 地理编码（Geocoding）

| 层 | 说明 |
|----|------|
| **是什么** | 把地名翻译成坐标（纬度 latitude、经度 longitude） |
| **在本文干什么** | 气象预报接口通常要坐标，不直接吃「杭州」两个字 |
| **怎么区分** | 编码失败（找不到城市）→ 工具返回「找不到城市…」，不要假装有气温 |

### `tool.invoke`（单测）

| 层 | 说明 |
|----|------|
| **是什么** | 不经过大模型，直接调用工具 |
| **在本文干什么** | 验证网络、解析 JSON、温度是否合理；再挂 Agent |
| **怎么区分** | 真实 API 下还要验证：外网通不通、超时/找不到城市时的错误文案 |

### docstring、`@tool`、`create_agent`

与 Day15 相同：docstring → 名片说明；`@tool` 包装；`tools=[get_weather]` 登记。  
`system_prompt` 仍是**软约束**（提醒「必须调工具、别编气温」）。

### Observation 里的气温从哪来

| 层 | 说明 |
|----|------|
| **是什么** | 工具函数返回值 |
| **在本文干什么** | 来自 Open-Meteo JSON 里的 `temperature_2m`（假模式下来自本地字典） |
| **怎么区分** | **不是**模型训练记忆里的数。Answer 应依据 Observation |

### `WEATHER_FAKE`（兜底，非主路径）

| 层 | 说明 |
|----|------|
| **是什么** | 环境变量：设为 `1` 时改走本地假字典 |
| **在本文干什么** | 飞机/无网/CI 时仍能演示 Agent 接线 |
| **怎么区分** | **不能**用假数据交差当作「已完成查询天气」。主验收必须看到 `来源：Open-Meteo` |

### MCP（边界）

上游资料会提到 MCP：另一种把工具暴露给模型的协议。本文用 LangChain `@tool` 完成目标；MCP **不实现**。

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- **外网**可访问 `open-meteo.com`  
- 集成 Agent 时需要 [Ollama](https://ollama.com/)（如 `qwen2:7b`）  
- 无需天气 API Key、无需 Docker  

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day16-custom-weather-tool && cd day16-custom-weather-tool
```

### `pyproject.toml`

```toml
[project]
name = "day16-custom-weather-tool"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langchain>=1.3.16",
    "langchain-ollama>=1.1.0",
    "langgraph>=0.4.0",
]
```

```bash
uv sync
```

> **Agent 入口版本**：LangChain ≥1.3 使用 `from langchain.agents import create_agent`，可用 `model="ollama:qwen2:7b"` 与 `system_prompt=`。网上旧文常见 `langgraph.prebuilt.create_react_agent`（参数多为 `prompt=`、常传 `ChatOllama` 实例），API 不同，**勿混用**。

### 核心：真实查询工具 `weather_tool.py`

```python
"""查天气：默认 Open-Meteo 真实 API；WEATHER_FAKE=1 时用假数据。"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from langchain.tools import tool

FAKE_WEATHER = {
    "北京": {"temp_c": 28, "condition": "晴"},
    "上海": {"temp_c": 24, "condition": "多云"},
    "杭州": {"temp_c": 22, "condition": "多云"},
}

WMO_ZH = {
    0: "晴",
    1: "主要晴朗",
    2: "局部多云",
    3: "阴",
    61: "小雨",
    63: "中雨",
    80: "阵雨",
    95: "雷暴",
    96: "雷暴伴冰雹",
}


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "day16-weather-tool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_weather_open_meteo(city: str) -> str:
    geo_q = urllib.parse.urlencode({"name": city, "count": 1, "language": "zh"})
    geo = _http_get_json(f"https://geocoding-api.open-meteo.com/v1/search?{geo_q}")
    results = geo.get("results") or []
    if not results:
        return f"找不到城市「{city}」，请换一个更常见的地名再试。"

    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    label = place.get("name") or city

    wx_q = urllib.parse.urlencode(
        {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code",
            "timezone": "auto",
        }
    )
    wx = _http_get_json(f"https://api.open-meteo.com/v1/forecast?{wx_q}")
    current = wx.get("current") or {}
    temp = current.get("temperature_2m")
    code = current.get("weather_code")
    if temp is None:
        return f"已定位到 {label}，但未拿到气温数据，请稍后重试。"

    condition = WMO_ZH.get(int(code), f"天气码 {code}") if code is not None else "未知"
    return f"{label}：{condition}，气温 {temp}°C（来源：Open-Meteo）"


@tool
def get_weather(city: str) -> str:
    """查询指定城市的当前天气（真实气温与天气状况）。

    参数:
        city: 城市名，例如「北京」「上海」「杭州」。
    """
    city = city.strip()
    if not city:
        return "请提供城市名。"
    if os.getenv("WEATHER_FAKE", "").strip() in {"1", "true", "TRUE", "yes"}:
        info = FAKE_WEATHER.get(city) or FAKE_WEATHER.get(city.lower())
        if not info:
            return f"暂无「{city}」的假数据。"
        return f"{city}：{info['condition']}，气温 {info['temp_c']}°C（假数据）"
    try:
        return fetch_weather_open_meteo(city)
    except urllib.error.URLError as e:
        return f"网络错误：{e}。可设 WEATHER_FAKE=1 兜底。"
    except Exception as e:  # noqa: BLE001
        return f"查询失败：{e}"


if __name__ == "__main__":
    for c in ("北京", "杭州"):
        print(c, "->", get_weather.invoke({"city": c}))
```

```bash
uv run python weather_tool.py
```

**期望**：输出含真实气温，且带 `来源：Open-Meteo`（数字会随天气变化）。

### 集成 Agent `weather_agent.py`

```python
from __future__ import annotations

import os
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from weather_tool import get_weather

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


def print_react_trace(messages: list) -> None:
    step = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for call in msg.tool_calls:
                step += 1
                print(f"Action {step}: {call['name']}({call['args']})")
        elif isinstance(msg, ToolMessage):
            print(f"Observation: {msg.content}")
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
            print(f"Answer: {msg.content}")
            break


question = sys.argv[1] if len(sys.argv) > 1 else "杭州天气怎么样？"
agent = create_agent(
    model=f"ollama:{OLLAMA_MODEL}",
    tools=[get_weather],
    system_prompt="你是天气助手。问天气必须调用 get_weather，禁止编造气温。城市名用中文。",
)
print(f"Q: {question}")
result = agent.invoke({"messages": [{"role": "user", "content": question}]})
print_react_trace(result["messages"])
```

```bash
uv run python weather_agent.py "杭州天气怎么样？"
```

**期望**：

```text
Action 1: get_weather({'city': '杭州'})
Observation: 杭州：…，气温 …°C（来源：Open-Meteo）
Answer: ...
```

---

## 新手坑

### 1. 只用假字典就当「查天气」做完了

| | |
|--|--|
| **问题** | 未满足「查询」——没有外部数据源 |
| **处理** | 主路径必须走 Open-Meteo（或等价真实 API）；假数据仅 `WEATHER_FAKE=1` |

### 2. 无网 / 超时

| | |
|--|--|
| **现象** | Observation 含「网络错误」 |
| **处理** | 检查网络；临时 `WEATHER_FAKE=1` 验证 Agent 接线；网络恢复后再跑真查询 |

### 3. 城市名找不到

| | |
|--|--|
| **现象** | 「找不到城市」 |
| **处理** | 换更常见地名；地理编码对生僻写法不敏感时需归一化（本篇保持简单） |

### 4. 忘了 `@tool` 或 `tools=[get_weather]`

模型只能瞎编气温；轨迹无 `get_weather`。

---

## 本文边界

**做了什么**：真实 Open-Meteo 查询 + `@tool` + Agent 集成 + 无网假数据兜底。  

**故意没展开**：付费天气 Key、MCP 实作、SQL 工具、tenacity 重试。

---

## 延伸阅读

- [Open-Meteo 文档](https://open-meteo.com/en/docs)  
- [LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools)  

---

## 收束

1. Day16 的硬目标是**会查**天气：工具函数里要有真实请求。  
2. `@tool` + `create_agent` 接线与 Day15 相同；变的是函数体。  
3. 先 `invoke` 确认 API，再让模型调用——Observation 里的温度来自服务，不来自模型空想。
