# Day43–47 Lesson 5 — 核心·串联（统一入口）

> 挂钩上游：**核心功能开发**收束  
> 入口就是 `step04_hybrid_ask.py` 的 `POST /ask`——不再新开大文件。

## 原理

一个 API 覆盖 Lesson 1 三类问句：

| 问句类型 | 期望 source |
|----------|-------------|
| 事务/状态（有 ORD/SKU 且库有行） | `db` |
| 政策/说明 | `faq` |
| 越界 / 两边都没有 | `none` + `need_human` |

## 带读（整段 `ask`）

打开 `step04_hybrid_ask.py` 的 `ask`：从上到下只有三条岔路——订单 → 商品 → 其余进 `faq_or_human`。  
**输入**：`AskRequest.q`；**输出**：`AskResponse` 四个字段。

## 本课动手

1. **验收两类**（服务仍应是 step04 @8043）：

```bash
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"SKU-88 有没有货？"}'

curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"满多少包邮？"}'
```

期望：前者 `source=db`；后者 `source=faq`。

2. **小改动**：在 `faq_or_human` 里，FAQ 命中时给 `answer` 加前缀 `【帮助中心】`（只改 FAQ 分支，别动 db 分支）。改完重启 uvicorn，再 curl「7 天内能退吗」，确认前缀出现且 `source` 仍是 `faq`。
