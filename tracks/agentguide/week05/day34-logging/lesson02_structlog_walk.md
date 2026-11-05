# Day34 Lesson 2 — 带读 JSON 配置

关键点在 `configure_json_logging()`：

1. `processors` 流水线：加 level、时间戳 → 最后 `JSONRenderer()`  
2. 一行调用 `log.info("request_done", path=..., status=...)`  
3. 终端出现**一行一个 JSON 对象**（可用 `jq` 解析）

口诀：**事件名 + 关键字字段**；不要把一句话糊在字符串里。
