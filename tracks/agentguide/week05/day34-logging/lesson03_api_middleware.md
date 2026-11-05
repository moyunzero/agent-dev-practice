# Day34 Lesson 3 — 中间件打请求日志

流程：

1. 请求进入 → 记开始时间、生成/透传 `request_id`
2. `call_next` 跑业务
3. `finally` 里 `log.info("request_done", method=..., path=..., status=..., duration_ms=...)`

验收看 **uvicorn 所在终端** 的 JSON 行，不是只看 curl 的 HTTP 响应。
