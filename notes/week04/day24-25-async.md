# 把 I/O 密集调用改成异步：提升并发吞吐（附 LLM 优化手段地图）

性能画像若显示时间花在「等模型 / 等 HTTP」，下一刀不只有缓存。  
当**很多不同请求同时在干等**时，同步代码会把等待串成一条队；**异步**让等待重叠，提高吞吐。  
本文目标：把系统中 I/O 密集型操作（如 API 调用）改成异步，并弄清它在 LLM 性能工具箱里的位置。

## 你将会得到什么

1. 一张 **LLM 应用核心性能优化手段**对照表（区别与何时用）  
2. 用 `asyncio` 看清：同步串行 vs `gather` 并发；以及 `async def` + `time.sleep` 的坑  
3. 把 FastAPI 同步 I/O 路由改成 `async def` + `await`，并用并发压测对比  

---

## 零基础名词表

> 建议先读完再动手。

### LLM 应用性能优化手段地图（先建立全貌）

| 手段 | 解决什么 | 不解决什么 | 何时用 |
|------|----------|------------|--------|
| **性能画像**（cProfile / py-spy） | 不知道慢在哪 | 本身不加速 | **任何优化之前**先量 |
| **响应缓存**（如 Redis） | 相同问句反复调模型 | 每个都是新问句 | 重复问答、FAQ 多 |
| **异步 / 并发**（asyncio、FastAPI async） | 多请求同时干等 I/O 时被堵死 | 单次调用不会 magically 变快 | 要提高 QPS / 并行 API |
| **批处理**（batch embed / rerank） | 一次一条调用开销太大 | 单条低延迟场景可能更糟 | 离线建库、大批量向量化 |
| **更快推理引擎**（如 vLLM） | 推理堆栈限制吞吐 | 不替代缓存与并发设计 | 有 GPU、要冲吞吐 |
| **压测与指标**（locust、QPS/P99） | 不知优化有没有用 | 不是优化手段本身 | 优化前后对比 |

```text
系统慢？
  ├─① 先画像 ──► CPU 狂算？还是等模型/网络？
  ├─ 相同问句多？ ──► ② 缓存响应
  ├─ 很多不同请求同时等 I/O？ ──► ③ 异步（本文）
  ├─ 海量 embed/rerank？ ──► ④ 批处理
  └─ 单次推理仍慢？ ──► ⑤ 换引擎；最后 ⑥ 压测证明
```

人话：**缓存 = 少干活；异步 = 干等时去干别的；批处理 = 一次干一捆；换引擎 = 把活干得更快。**

### I/O 密集 vs CPU 密集

| | **I/O 密集** | **CPU 密集** |
|--|--------------|--------------|
| **是什么** | 时间花在等网络、磁盘、模型服务 | 时间花在本地狂算 |
| **在本文** | `sleep` / HTTP / 调 Ollama 都属于「干等」 | 大循环哈希等 |
| **异步是否对症** | **对**：等待时可切换协程 | 通常不对；要多进程/更快算法 |

### 同步 vs 异步 / 事件循环 / await

| 词 | 是什么 | 在本文干什么 |
|----|--------|--------------|
| **同步** | 调用返回前，当前线程卡住 | `time.sleep`、同步 `httpx.get` |
| **异步** | `await` 时把控制权交回事件循环 | `await asyncio.sleep`、`AsyncClient` |
| **事件循环** | 调度众多协程的「调度员」 | `asyncio.run` / uvicorn 内部在跑 |
| **`asyncio.gather`** | 同时推进多个协程 | 3 次 API 干等重叠成约 max(延迟) |

### FastAPI 路由：`def` vs `async def`

| 写法 | 含义 | 注意 |
|------|------|------|
| `def` + 阻塞 I/O | 改造前常见写法 | uvicorn 常丢进**线程池**，并发时也可能重叠，别被表象骗 |
| `async def` + `await` 真异步 | **推荐的 I/O 改造后** | 等待可重叠，不堵 loop |
| `async def` + `time.sleep` | **反例** | 堵死事件循环，并发≈串行 |

改造通常改**两处**：`def` → `async def`；阻塞调用 → `await` 异步 API。

---

## 环境准备

- Python 3.12+、[uv](https://github.com/astral-sh/uv)  
- 本文用 `asyncio.sleep` 假装下游 API/模型 I/O，**不强制**本机 Ollama  

`pyproject.toml`：

```toml
[project]
name = "day24-25-async"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn>=0.32.0",
  "httpx>=0.27.0",
]
```

```bash
uv sync
```

---

## 步骤 1：同步串行 vs 异步并发

`step01_sync_vs_async.py`：

```python
from __future__ import annotations

import asyncio
import time


def sync_call(name: str, delay: float) -> str:
    print(f"  [sync] {name} 开始等 {delay}s…")
    time.sleep(delay)
    print(f"  [sync] {name} 结束")
    return name


async def async_call(name: str, delay: float) -> str:
    print(f"  [async] {name} 开始等 {delay}s…")
    await asyncio.sleep(delay)
    print(f"  [async] {name} 结束")
    return name


def run_sync_serial() -> None:
    t0 = time.perf_counter()
    sync_call("A", 0.4)
    sync_call("B", 0.4)
    sync_call("C", 0.4)
    print(f"同步串行总耗时: {time.perf_counter() - t0:.2f}s\n")


async def run_async_concurrent() -> None:
    t0 = time.perf_counter()
    await asyncio.gather(
        async_call("A", 0.4),
        async_call("B", 0.4),
        async_call("C", 0.4),
    )
    print(f"异步并发总耗时: {time.perf_counter() - t0:.2f}s\n")


if __name__ == "__main__":
    print("=== 1) 同步串行 ===")
    run_sync_serial()
    print("=== 2) 异步并发 ===")
    asyncio.run(run_async_concurrent())
```

```bash
uv run python step01_sync_vs_async.py
```

**期望**：同步约 **1.2s**；异步约 **0.4s**。异步没有让「单次 0.4s」变短，只是三次重叠。

---

## 步骤 2：多路 API 与「假异步」陷阱

`step02_gather_api.py`（核心对比）：

```python
import asyncio
import time


def call_api_sync(name: str) -> str:
    time.sleep(0.35)
    return f"ok-{name}"


async def call_api_async(name: str) -> str:
    await asyncio.sleep(0.35)
    return f"ok-{name}"


async def call_api_wrong(name: str) -> str:
    time.sleep(0.35)  # 错误：堵死循环
    return f"ok-{name}"
```

分别测：同步串行、`gather` 真异步、`gather` + `time.sleep`。

```bash
uv run python step02_gather_api.py
```

**期望**：串行 ≈1.05s；`gather` ≈0.35s；错误写法仍 ≈1.1s。  
结论：名字叫 `async` 不够，必须 `await` **真异步 I/O**。

---

## 步骤 3：FastAPI 同步接口 → 异步

`main_api.py`：

```python
from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI

app = FastAPI(title="day24-25-async")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/sync-ask")
def sync_ask(q: str = "hi") -> dict:
    """改造前：同步 + 阻塞。"""
    time.sleep(0.4)
    return {"mode": "sync-def", "q": q, "answer": f"echo:{q}"}


@app.get("/async-ask")
async def async_ask(q: str = "hi") -> dict:
    """改造后：async def + await。"""
    await asyncio.sleep(0.4)
    return {"mode": "async-await", "q": q, "answer": f"echo:{q}"}


@app.get("/async-block")
async def async_block(q: str = "hi") -> dict:
    """反例：async 里写 time.sleep。"""
    time.sleep(0.4)
    return {"mode": "async-block", "q": q, "answer": f"echo:{q}"}
```

终端 1：

```bash
uv run uvicorn main_api:app --port 8024
```

终端 2 — `step03_bench_client.py`：对 `/async-ask` 与 `/async-block` 各打 3 个并发请求：

```bash
uv run python step03_bench_client.py
```

**期望示例**：

```text
并发 3 × /async-ask   (await) : 0.42s
并发 3 × /async-block (sleep) : 1.23s
```

`/async-ask` 才是改造成功；`/async-block` 会堵事件循环。

生产里把同步 `httpx` / SDK 换成 `AsyncClient`、`ainvoke` 等，同一套思想。

---

## 新手向坑

### 1. 以为 async 会让单次 Ollama 从 30s 变 3s

**不会。** 单次仍要等模型；要降单次延迟看缓存、更小模型或更快引擎。异步解决的是**多请求一起等**时的吞吐。

### 2. `async def` 里写了同步阻塞

**现象**：并发总时间≈相加。  
**处理**：换成 `await` 异步 API；或把阻塞丢进线程池（进阶，本文不展开）。

### 3. FAQ 场景只上异步不上缓存

相同问句应优先**缓存**（命中近 0 成本）；异步无法把「又算一遍」变成「不算」。

### 4. 改了代码没重启 uvicorn

无 `--reload` 时改 sleep 参数不生效；重启后再压测。

---

## 边界：做了什么 / 故意没做什么

**做了**：优化手段地图；asyncio 串行 vs gather；FastAPI I/O 异步改造与反例压测。

**没做**：真实 Ollama `ainvoke` 压测（可自行替换 sleep）；完整 aiohttp 爬虫；uvloop；批处理 / vLLM / locust（后续天）。

---

## 小结

| 步骤 | 要点 |
|------|------|
| 地图 | 画像 → 缓存 → 异步 → 批处理 → 引擎 → 压测 |
| 异步本质 | 干等可重叠；不加速单次 CPU/单次推理本身 |
| 改造两处 | `async def` + `await` 真异步 I/O |
| 大忌 | `async def` + `time.sleep` / 同步 HTTP |

先分清「少干活 / 重叠等待 / 一次干一捆 / 干得更快」，再动手改路由——优化才不会用错刀。
