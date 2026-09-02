"""第 1 课：自定义「查天气」工具 — 调真实 Open-Meteo API（免 Key）。

默认走外网真实查询（上游目标：编写查询天气的工具）。
仅当设置 WEATHER_FAKE=1 时用本地字典（无网/CI 兜底）。
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

from langchain.tools import tool

# 无网兜底（WEATHER_FAKE=1 时使用）
FAKE_WEATHER = {
    "北京": {"temp_c": 28, "condition": "晴"},
    "上海": {"temp_c": 24, "condition": "多云"},
    "深圳": {"temp_c": 31, "condition": "雷阵雨"},
    "杭州": {"temp_c": 22, "condition": "多云"},
}

# WMO weather interpretation codes（节选，够教学用）
WMO_ZH = {
    0: "晴",
    1: "主要晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    80: "阵雨",
    95: "雷暴",
    96: "雷暴伴冰雹",
}


def _http_get_json(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "day16-weather-tool/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_weather_open_meteo(city: str) -> str:
    """地理编码 + 当前气温：Open-Meteo（免费、无需 API Key）。"""
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


def fetch_weather_fake(city: str) -> str:
    key = city.strip()
    info = FAKE_WEATHER.get(key) or FAKE_WEATHER.get(key.lower())
    if not info:
        return f"暂无「{city}」的假数据。已知：北京、上海、深圳、杭州。"
    return f"{city}：{info['condition']}，气温 {info['temp_c']}°C（假数据）"


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
        return fetch_weather_fake(city)

    try:
        return fetch_weather_open_meteo(city)
    except urllib.error.URLError as e:
        return f"网络错误，无法查询「{city}」天气：{e}。可设 WEATHER_FAKE=1 用假数据兜底。"
    except TimeoutError:
        return f"查询「{city}」超时。可稍后重试，或设 WEATHER_FAKE=1。"
    except Exception as e:  # noqa: BLE001 — 工具应对 Agent 返回可读错误
        return f"查询「{city}」失败：{e}"


def main() -> None:
    mode = "假数据" if os.getenv("WEATHER_FAKE", "").strip() in {"1", "true", "TRUE", "yes"} else "Open-Meteo 真实 API"
    print(f"=== 第 1 课：自定义查天气工具（模式：{mode}）===\n")
    print("工具名片:")
    print(f"  名: {get_weather.name}")
    print(f"  说明: {get_weather.description}")
    schema = get_weather.args_schema.model_json_schema()
    print(f"  参数: {list(schema.get('properties', {}).keys())}")
    print()

    print("--- 直接 invoke（不经过大模型）---")
    for city in ("北京", "上海", "杭州"):
        out = get_weather.invoke({"city": city})
        print(f"  get_weather({city!r}) -> {out}")

    print()
    print("要点：工具逻辑 = 普通 Python（这里会发 HTTP）；@tool 把它变成 Agent 名片。")
    print("默认真实查询 Open-Meteo；无网时：WEATHER_FAKE=1 uv run python step01_weather_tool.py")


if __name__ == "__main__":
    main()
