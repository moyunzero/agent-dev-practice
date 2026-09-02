# 用 OpenAI API 做 Function Calling：让模型「点菜」，本地函数「炒菜」

Day15–17 用 LangChain 的 `@tool` + `create_agent`，框架帮你填好了工具协议。  
上游 Day18 要求：**使用 OpenAI API，实现一个能根据用户问题调用函数的 Agent**。本文回到协议原貌——用官方 `openai` Python SDK，走 Chat Completions 的 `tools` / `tool_calls`：模型只负责声明「调哪个函数、参数是什么」；**真正执行 Python 的是你的程序**；再把结果以 `role: tool` 交回模型，写出最终答案。

默认对接 **Ollama 的 OpenAI 兼容接口**（与本系列 Day1/2 相同），换真 OpenAI 只需改 Key / base_url / model。

## 你将会得到什么

1. 分清 `tools`（你发的菜单）与 `tool_calls`（模型点的单）  
2. 手写两轮循环：请求 → 执行本地函数 → 再请求 → 最终 Answer  
3. 用订单查询示例验证：改本地数据后，答案跟着变  
4. 避开：没有 tool_calls 却假装查库；把 FC 理解成「模型能跑你的代码」  

---

## 零基础名词表

> 建议先读完再动手。

### Function Calling（函数调用 / Tool Calling）

| 层 | 说明 |
|----|------|
| **是什么** | 一种约定：模型在回复里声明要调用的函数名与参数；由**应用侧**执行函数后再继续对话 |
| **在本文干什么** | 用户问订单状态 → 模型点 `get_order_status` → 本地查字典 → 模型写成客服话术 |
| **怎么区分** | **不是**模型在云端直接跑你的 Python。没有你的执行步骤，就只有「点单」，没有「出菜」 |

类比餐厅：

| 餐厅 | Function Calling |
|------|------------------|
| 菜单 | `tools`（JSON Schema） |
| 顾客点单 | `tool_calls` |
| 厨房 | 你的 Python 函数 |
| 上菜后再解释给客人 | 第二轮模型读到结果后的 `content` |

### `tools`（发给 API 的说明书）

| 层 | 说明 |
|----|------|
| **是什么** | 请求体里的工具列表：名称、描述、参数的 JSON Schema |
| **在本文干什么** | 声明 `get_order_status(order_id: string)` |
| **怎么区分** | **由你的程序发给 API**，不是模型生成的 |

### `tool_calls`（模型返回的点单）

| 层 | 说明 |
|----|------|
| **是什么** | assistant 消息里的数组：`name` + `arguments`（多为 JSON 字符串）+ `id` |
| **在本文干什么** | 例如 `get_order_status` + `{"order_id":"ORD-1001"}` |
| **怎么区分** | **由模型产生**。没有 `tool_calls` 时，不要擅自执行函数却声称走了 FC |

### `role: tool`（第二轮回传）

| 层 | 说明 |
|----|------|
| **是什么** | 把函数返回值放进对话历史，并带上对应的 `tool_call_id` |
| **在本文干什么** | 把 `{"status":"运输中",...}` 交给模型，供其写最终答案 |
| **怎么区分** | 第一轮常只有点单；没有工具结果，模型无法如实引用物流状态 |

### OpenAI API 与兼容接口

| 层 | 说明 |
|----|------|
| **是什么** | 官方 Chat Completions HTTP 形状；`openai` SDK 封装了它 |
| **在本文干什么** | `client.chat.completions.create(..., tools=..., tool_choice="auto")` |
| **怎么区分** | Ollama `http://127.0.0.1:11434/v1` 可兼容同一写法；真云用 `https://api.openai.com/v1` + 真实 API Key。协议相同，计费与模型能力不同 |

### 与 LangChain `@tool` / `create_agent` 的关系

| 层 | 说明 |
|----|------|
| **是什么** | 框架在底层仍多走 Tool Calling；帮你生成 schema、拼消息、跑循环 |
| **在本文干什么** | 对照学习：今天手动做框架默默做的事 |
| **怎么区分** | Day15 学「会用 Agent」；Day18 学「协议长什么样」 |

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- 默认：[Ollama](https://ollama.com/) 已启动，模型支持 tools（如 `qwen2:7b`）  
- 或：OpenAI 账号与 `OPENAI_API_KEY`  

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day18-function-calling && cd day18-function-calling
```

### `pyproject.toml`

```toml
[project]
name = "day18-function-calling"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["openai>=1.40.0"]
```

```bash
uv sync
```

### 最小 Agent：`fc_agent.py`

```python
"""OpenAI SDK Function Calling 两轮循环。"""

from __future__ import annotations

import json
import os
import sys

from openai import OpenAI

ORDERS = {
    "ORD-1001": {"status": "运输中", "city": "杭州", "eta": "2026-09-02"},
    "ORD-1002": {"status": "待支付", "city": "上海", "eta": None},
}


def get_order_status(order_id: str) -> dict:
    key = order_id.strip().upper()
    info = ORDERS.get(key)
    if not info:
        return {"order_id": key, "error": "订单不存在"}
    return {"order_id": key, **info}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": "根据订单号查询物流状态、收件城市与预计到达日。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "订单号，例如 ORD-1001",
                    }
                },
                "required": ["order_id"],
            },
        },
    }
]


def main() -> None:
    client = OpenAI(
        base_url=os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1"),
        api_key=os.getenv("OPENAI_API_KEY", "ollama"),
    )
    model = os.getenv("OPENAI_MODEL", os.getenv("OLLAMA_MODEL", "qwen2:7b"))
    question = sys.argv[1] if len(sys.argv) > 1 else "帮我查一下订单 ORD-1001 现在什么状态？"

    messages = [
        {
            "role": "system",
            "content": "你是客服。查订单必须调用 get_order_status，禁止编造。",
        },
        {"role": "user", "content": question},
    ]

    # 第 1 轮：带 tools
    resp1 = client.chat.completions.create(
        model=model,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )
    msg1 = resp1.choices[0].message
    print("finish_reason:", resp1.choices[0].finish_reason)
    if not msg1.tool_calls:
        print("无 tool_calls，结束。Answer:", msg1.content)
        return

    messages.append(msg1.model_dump(exclude_none=True))

    # 本地执行
    for call in msg1.tool_calls:
        args = json.loads(call.function.arguments or "{}")
        result = get_order_status(**args)
        print("函数返回:", result)
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    # 第 2 轮：生成最终答案
    resp2 = client.chat.completions.create(model=model, messages=messages)
    print("Answer:", resp2.choices[0].message.content)


if __name__ == "__main__":
    main()
```

```bash
uv run python fc_agent.py
```

**期望**：出现 `get_order_status`、函数返回含「运输中」（或你改过的状态）、Answer 引用该状态。

切真 OpenAI 示例：

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
uv run python fc_agent.py
```

---

## 新手坑

### 1. 以为模型会自己执行函数

| | |
|--|--|
| **错觉** | 发了 `tools` 就等于查完订单 |
| **事实** | 必须解析 `tool_calls` 并在本地调用；再发 `role: tool` |

### 2. 没有 `tool_calls` 仍去查库并宣称成功

| | |
|--|--|
| **问题** | 绕过了协议，答案与「模型是否点单」脱节 |
| **处理** | 无 `tool_calls` 就结束或只展示模型原文 |

### 3. 改了 `ORDERS` 但 Answer 仍是旧状态

| | |
|--|--|
| **排查** | 看终端「函数返回」是否已是新值；若函数对新、Answer 旧，多半是第二轮模型胡编——加强 system，或换更强模型 |

### 4. 模型不支持 tools

| | |
|--|--|
| **现象** | 始终无 `tool_calls` |
| **处理** | 换支持 tool calling 的模型，或改用真 OpenAI |

---

## 本文边界

**做了什么**：OpenAI Chat Completions Function Calling 两轮 Agent；订单查询；兼容 Ollama。  

**故意没展开**：并行多 tool_calls 复杂编排、LangChain 再封装、Memory / 重试专题。

---

## 延伸阅读

- [OpenAI Function Calling 指南](https://platform.openai.com/docs/guides/function-calling)  
- [GPT Best Practices](https://platform.openai.com/docs/guides/gpt-best-practices)  

---

## 收束

1. **FC = 点菜协议**：模型点单，本地炒菜，再让模型上桌解释。  
2. **`tools` 你发，`tool_calls` 模型回**；别记反。  
3. **第二轮 `role: tool`** 把函数结果喂回去，答案才能有据可依。
