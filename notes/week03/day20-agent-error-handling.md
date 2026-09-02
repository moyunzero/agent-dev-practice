# 给 Agent 工具加韧性：tenacity 重试 + 降级策略

Agent 一调外网或内部 API，就会碰上超时、偶发 5xx、连接抖动。若工具失败一次就抛异常，整轮对话可能直接中断，用户什么都看不到。  
上游 Day20 目标：**为工具调用添加重试机制（`tenacity` 库）和降级策略**。本文用可控的「假抖动查价 API」演示：先看无重试如何炸；再用 `@retry` 扛住偶发失败；重试耗尽后返回缓存价；最后把同一套逻辑挂进 `create_agent` 的 `@tool`。

## 你将会得到什么

1. 分清：**适合重试**的瞬时错误 vs **不适合重试**的业务/参数错误  
2. 用 `tenacity` 配置 `stop`（试几次）与 `wait`（隔多久）  
3. 实现 **先重试、再降级**，保证「有答复」  
4. 把韧性写在**工具边界**，让模型只负责调工具与说话  

---

## 零基础名词表

> 建议先读完再动手。

### 瞬时错误 vs 确定错误

| 层 | 说明 |
|----|------|
| **是什么** | 瞬时：超时、网络抖动、偶发 5xx，过一会儿再试可能好。确定：参数写错、SKU 不存在、权限拒绝，再试一百次也一样 |
| **在本文干什么** | 我们只对 `ConnectionError` 重试；参数类错误不该靠重试「碰运气」 |
| **怎么区分** | 问自己：「再等半秒重做同一请求，有没有机会成功？」有 → 可重试；没有 → 立刻报错或换路径 |

### 重试（retry）

| 层 | 说明 |
|----|------|
| **是什么** | 同一操作失败后再做若干次，常配合短暂等待 |
| **在本文干什么** | `fail_times=2` 时前两次失败；最多试 3 次 → 第 3 次拿到实时价 |
| **怎么区分** | 重试解决「偶发」；解决不了「服务彻底挂了」——那是降级的事 |

### tenacity

| 层 | 说明 |
|----|------|
| **是什么** | Python 常用重试库，用装饰器 `@retry(...)` 包住函数 |
| **在本文干什么** | `retry_if_exception_type(ConnectionError)` + `stop_after_attempt(3)` + `wait_fixed(...)` |
| **怎么区分** | `stop` = 最多试几次（含第一次）；`wait` = 两次尝试之间等多久。两者不是一回事 |

### 降级（fallback）

| 层 | 说明 |
|----|------|
| **是什么** | 主路径（实时查价）不可用时的备用结果：缓存价、默认文案、「暂时不可用」 |
| **在本文干什么** | 重试仍失败 → 读本地 `CACHE_PRICE`，返回「降级缓存价」字符串 |
| **怎么区分** | 降级不是「大模型不支持」，而是**工具/外网仍失败**时，仍给用户可用答复。顺序：**先 retry，耗尽再 fallback** |

### 工具边界上的韧性

| 层 | 说明 |
|----|------|
| **是什么** | 把重试与降级写在工具函数内部；模型只看到返回的字符串 |
| **在本文干什么** | `@tool lookup_price` 内部调带 `@retry` 的查价；失败则 `return` 降级文案 |
| **怎么区分** | 不要指望模型「自己决定再试」——重试是确定性工程，模型负责选工具与组织话术 |

```text
用户问价
  → Agent 调 lookup_price
      → tenacity 重试实时 API
      → 成功：返回「现价 128」
      → 耗尽仍失败：返回「降级缓存价 99」
  → 模型根据工具字符串说一句导购话
```

| 方式 | 对 Agent 的影响 |
|------|-----------------|
| 工具**抛异常**且外层未兜住 | 整轮可能中断，模型拿不到 tool 结果 |
| 工具**返回说明字符串**（含降级） | 结果进对话，模型仍能组织答复 |

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- 第 1–2 课：**不需要**大模型  
- 第 3 课：本机 [Ollama](https://ollama.com/) + 支持 tools 的模型（如 `qwen2:7b`）

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day20-agent-error-handling && cd day20-agent-error-handling
```

### `pyproject.toml`

```toml
[project]
name = "day20-agent-error-handling"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "langchain>=1.0",
  "langchain-ollama>=0.3",
  "langgraph>=0.2",
  "tenacity>=8.0",
]
```

```bash
uv sync
```

### `flaky_price.py`（模拟抖动 API）

```python
from __future__ import annotations

_CALL_COUNT = 0
CACHE_PRICE = {"SKU-1": 99.0, "SKU-2": 49.0}


def reset_counter() -> None:
    global _CALL_COUNT
    _CALL_COUNT = 0


def get_call_count() -> int:
    return _CALL_COUNT


def fetch_price_flaky(sku: str, *, fail_times: int = 2) -> str:
    """前 fail_times 次抛 ConnectionError，之后返回实时价。"""
    global _CALL_COUNT
    _CALL_COUNT += 1
    attempt = _CALL_COUNT
    if attempt <= fail_times:
        raise ConnectionError(f"模拟网络抖动：第 {attempt} 次调用失败 (sku={sku})")
    price = {"SKU-1": 128.0, "SKU-2": 56.0}.get(sku.upper(), 0.0)
    return f"{sku.upper()} 现价 {price} 元（实时）"
```

记住：`fail_times=N` → 失败 N 次，第 **N+1** 次才成功。

### 对照：无重试直接炸

```python
from flaky_price import fetch_price_flaky, reset_counter

reset_counter()
try:
    print(fetch_price_flaky("SKU-1", fail_times=2))
except ConnectionError as e:
    print(f"捕获异常: {e}")
```

期望：第一次就失败，看不到价格。

### `demo_tenacity_fallback.py`（重试 + 降级）

```python
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)
from flaky_price import CACHE_PRICE, fetch_price_flaky, get_call_count, reset_counter


@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.15),
    reraise=True,
)
def fetch_price_with_retry(sku: str) -> str:
    print(f"  …尝试调用 (已累计 {get_call_count() + 1} 次)")
    return fetch_price_flaky(sku, fail_times=2)


def fetch_price_resilient(sku: str) -> str:
    try:
        return fetch_price_with_retry(sku)
    except (ConnectionError, RetryError) as e:
        cached = CACHE_PRICE.get(sku.upper())
        if cached is not None:
            return f"{sku.upper()} 暂不可用实时价，降级缓存价 {cached} 元（原因: {e}）"
        return f"{sku.upper()} 查询失败且无缓存，请稍后再试。（{e}）"


reset_counter()
print(fetch_price_resilient("SKU-1"))  # 期望：3 次尝试后「现价 128.0」
```

把 `stop_after_attempt(3)` 改成 `2` 再跑：两次都失败 → 应出现 **降级缓存价 99.0**。验证完改回 `3`。

彻底失败时的降级（示意）：

```python
@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.05),
    reraise=True,
)
def always_fail(sku: str) -> str:
    raise ConnectionError("模拟服务彻底挂了")

try:
    always_fail("SKU-2")
except ConnectionError as e:
    print(f"SKU-2 降级缓存价 {CACHE_PRICE['SKU-2']} 元（{e}）")
```

### 挂进 Agent：`demo_agent_resilient.py`

```python
import os
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import AIMessage
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed
from flaky_price import CACHE_PRICE, fetch_price_flaky, reset_counter

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


@retry(
    retry=retry_if_exception_type(ConnectionError),
    stop=stop_after_attempt(3),
    wait=wait_fixed(0.1),
    reraise=True,
)
def _fetch_live(sku: str) -> str:
    return fetch_price_flaky(sku, fail_times=2)


@tool
def lookup_price(sku: str) -> str:
    """查询商品现价。参数 sku 例如 SKU-1 或 SKU-2。失败时会重试，仍失败则返回缓存价。"""
    try:
        return _fetch_live(sku)
    except ConnectionError as e:
        cached = CACHE_PRICE.get(sku.upper())
        if cached is not None:
            return f"{sku.upper()} 实时失败，降级缓存价 {cached} 元。（{e}）"
        return f"查询失败：{e}"


reset_counter()
agent = create_agent(
    model=f"ollama:{OLLAMA_MODEL}",
    tools=[lookup_price],
    system_prompt="你是导购。问价格必须调用 lookup_price，禁止编造数字。用一句话回答。",
)
result = agent.invoke({"messages": [{"role": "user", "content": "SKU-1 现在多少钱？"}]})
for msg in result["messages"]:
    if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
        print("Answer:", msg.content)
        break
```

期望：Answer 中出现约 **128** 的实时价（工具内部已完成重试）。

```bash
uv run python demo_agent_resilient.py
```

---

## 新手向坑

| 现象 | 原因 | 处理 |
|------|------|------|
| 改成 `stop_after_attempt(2)` 后不再出 128，而是 99 缓存价 | `fail_times=2` 需要第 3 次才成功；只允许 2 次 → 必走降级 | 这是预期；教学验证后改回 `3` |
| Agent 编造价格、不调工具 | 模型偶发忽略 system / tool 描述 | 强调「必须调用 lookup_price」；再跑一次；换支持 tools 的模型 |
| 对「SKU 不存在」也疯狂重试 | 把确定错误当成瞬时错误 | 只对网络类异常 `retry_if_exception_type`；业务错误直接返回说明 |

---

## 边界：做了什么 / 故意没做什么

**做了**

- 可控假失败 + `tenacity` 重试  
- 重试耗尽后的缓存价降级  
- 韧性写在 `@tool` 内并挂进 `create_agent`  

**故意没做**

- 生产级熔断、全链路 tracing  
- LangChain `ToolRetryMiddleware` 细讲（知悉即可）  
- 解析错误（output parser）全专题  
- 强制真实外网 API（用假抖动更利于对照）  

---

## 一句话收束

**偶发失败靠 tenacity 再试；试够了还挂就降级给答复；把这套写在工具里，Agent 才扛得住真实世界。**
