# 用 Locust 和 JMeter 压测：读懂 QPS、P99，并对比优化前后

改完缓存、异步、批处理、推理引擎之后，最怕两件事：**凭感觉说「好像快了」**，以及 **只看平均、不看尾部**。  
性能压测就是用工具假装很多用户同时打接口，用数字回答：

> 系统每秒能扛多少请求？最惨的那 1% 用户要等多久？失败了多少？

本文用 **Locust（Python）** 和 **JMeter（Java 生态）** 对同一套本地 FastAPI 做压测，记录 **QPS（≈RPS）** 与 **P99**，并对比「真异步」与「async 里写阻塞」的优化前后差异。最后用一张地图收束整周性能优化手段。

## 你将会得到什么

1. 用人话解释 **QPS / RPS、P50、P99、失败率、Ramp-up**  
2. 跑通 **Locust Web UI** 与 **JMeter 非 GUI**，并在报告里指出对应数字  
3. 在相同负载下对比 `/async-ask` vs `/async-block`，解释谁更好、为什么  
4. 把压测放进「画像 → 缓存 → 异步 → 批 → 引擎 → 压测」整周链路里  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### 性能压测（Load testing）

| 层 | 说明 |
|----|------|
| **是什么** | 用工具模拟大量用户/请求打系统，观察吞吐、延迟、错误是否达标 |
| **在本文干什么** | 不猜「异步改好了没」；用 Locust / JMeter 打本地 FastAPI，读 QPS 与 P99 |
| **怎么区分** | **功能测试**问「对不对」；**压测**问「多人同时用时还扛不扛得住」。也不同于单机 `time.perf_counter` 打 8 次——压测工具可持续加压并出标准报告 |

### QPS / RPS（吞吐）

| 层 | 说明 |
|----|------|
| **是什么** | **QPS** = Queries Per Second，每秒处理多少查询/请求。工具里常写 **RPS**（Requests Per Second）。本文把二者当作同一类「吞吐」指标 |
| **在本文干什么** | Locust 看 **RPS**；JMeter 看 **Throughput（/s）**。数字越高，单位时间清的单越多 |
| **怎么区分** | **延迟**问「这一问等多久」；**QPS** 问「系统每秒能干多少活」。QPS 高不等于每个人都爽——还要看 P99 和失败率 |

### 延迟百分位：P50 / P95 / P99

| 层 | 说明 |
|----|------|
| **是什么** | 把所有请求的耗时从小到大排好：排在 50% / 95% / 99% 位置上的那个值。**P99** = 99% 的请求不超过这么久，也就是「最慢那 1% 有多惨」 |
| **在本文干什么** | Locust 看 **99%ile**；JMeter HTML 报告里看 **99th pct**（或 Aggregate Report 的 99% Line） |
| **怎么区分** | **平均值**会被少数极慢请求拉歪，也可能掩盖尾部灾难。生产常盯 **P99**：**QPS 看容量，P99 看尾部体验** |

```text
100 次请求按耗时排序：
  第 50 个 → P50（普通人）
  第 99 个 → P99（倒霉的那 1%）
```

### 失败率（Error / Failure rate）

| 层 | 说明 |
|----|------|
| **是什么** | 超时、连接失败、HTTP 5xx 等占全部请求的比例 |
| **在本文干什么** | 报告里 **Failures / Error%** 必须先看；失败 20% 时，高 QPS 没有意义 |
| **怎么区分** | 「请求发出去了」≠「业务成功」。读数顺序：**失败率 → QPS → P99** |

### 虚拟用户、Spawn rate、Ramp-up

| 层 | 说明 |
|----|------|
| **是什么** | **虚拟用户** = 工具模拟的并发客户端数量。**Spawn rate**（Locust）= 每秒新加几个用户。**Ramp-up**（JMeter）= 全部用户在多少秒内从 0 爬到满员 |
| **在本文干什么** | 例：10 用户；Locust spawn=2；JMeter Ramp-up=5 秒。控制「压力怎么爬上去」 |
| **怎么区分** | Ramp-up / spawn **不是**「每个请求之间歇多久」（那是 wait_time / think time）。Ramp-up=0 表示几乎同时冲进来，冲击更大 |

```text
Threads=10，Ramp-up=5s：
  大约每 0.5 秒多 1 人，第 5 秒 10 人到齐

Locust spawn rate=2：
  大约每秒多 2 个用户，直到达到设定总人数
```

### Locust

| 层 | 说明 |
|----|------|
| **是什么** | 用 **Python** 写用户行为的开源压测工具，自带 Web UI（默认 `:8089`） |
| **在本文干什么** | 写 `HttpUser` + `@task`，对 `/async-ask` 与 `/async-block` 加压，读 RPS 与 99%ile |
| **怎么区分** | 场景在代码里改，适合开发自测；和「手写线程狂 curl」相比，自带统计与加压控制 |

### JMeter

| 层 | 说明 |
|----|------|
| **是什么** | Apache 的压测工具，常用 **GUI 配测试计划**（`.jmx`），也可无界面命令行跑 |
| **在本文干什么** | 用 HTTP Request 打同一 API；命令行出 HTML 报告，读 Throughput 与 99th |
| **怎么区分** | 与 Locust **测的是同一类指标**；差别在「怎么编排压力」（Python 脚本 vs GUI/`.jmx`），不是「一个只测 QPS、一个只测 P99」 |

### 优化前后对照（公平压测）

| 层 | 说明 |
|----|------|
| **是什么** | 只改「要证明的那一处」，其余负载与环境尽量锁死，再比两组数字 |
| **在本文干什么** | 同一用户数 / 爬升 / 循环 / 工具 / 机器，只换路径：`/async-ask` vs `/async-block` |
| **怎么区分** | 一边开缓存、一边连真 LLM、一边换机器——对比无效。必须锁死负载形态、请求内容、环境与读数口径 |

### 被测接口：真异步 vs 堵事件循环

| 路径 | 写法 | 并发时会发生什么 |
|------|------|------------------|
| `/async-ask` | `await asyncio.sleep(0.4)` | 等待时让出事件循环，多请求可重叠 → **优化后** |
| `/async-block` | `async def` 里 `time.sleep(0.4)` | 阻塞整个 loop，请求近似串行 → **优化前反例** |

```text
假用户 × N  ──HTTP──►  FastAPI :8024
                            │
                   Locust / JMeter 统计
                            │
                 RPS/Throughput、P99、Error%
```

### 和第 4 周其它手段的关系

| 手段 | 解决什么 | 和压测的关系 |
|------|----------|--------------|
| 画像（cProfile 等） | 慢在哪 | 压测前/后都可验证 |
| Redis 缓存 | 相同问句少干活 | 压测时注意 MISS/HIT 别混 |
| 异步 | 等待时不堵别人 | **本文对照点** |
| 批处理 | 客户端一次干一捆 | 另测 embed/rerank |
| vLLM 等引擎 | 推理算力侧更快 | 可对推理端口压测 |
| **压测** | **用数字验收** | 本周收官 |

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- Java 11+（跑 JMeter；`java -version` 能出版本即可）  
- 两个终端：一个跑 FastAPI，一个跑压测工具  

目录建议：

```text
day28-load-test/
  pyproject.toml          # locust
  locustfile_async_ask.py
  locustfile_async_block.py
  jmeter_async_ask.jmx
  jmeter_async_block.jmx
  main_api.py             # 被测服务（也可单独目录）
```

`pyproject.toml`：

```toml
[project]
name = "day28-load-test"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn>=0.32.0",
  "locust>=2.32.0",
]
```

---

## 被测服务（先起这个）

完整 `main_api.py`（与本文对照直接相关的是后两个路由）：

```python
"""本地被测 FastAPI：真异步 vs 堵事件循环。"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI

app = FastAPI(title="day28-load-target")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/async-ask")
async def async_ask(q: str = "hi") -> dict:
    await asyncio.sleep(0.4)
    return {"mode": "async-await", "q": q, "answer": f"echo:{q}"}


@app.get("/async-block")
async def async_block(q: str = "hi") -> dict:
    time.sleep(0.4)  # 错误示范：堵死 event loop
    return {"mode": "async-block", "q": q, "answer": f"echo:{q}"}
```

启动：

```bash
uv sync
uv run uvicorn main_api:app --port 8024
```

验收：

```bash
curl -s 'http://127.0.0.1:8024/health'
curl -s 'http://127.0.0.1:8024/async-ask?q=hi'
```

---

## Locust：最小压测

### 脚本（优化后：`/async-ask`）

```python
"""Locust：打 /async-ask。"""

from __future__ import annotations

from locust import HttpUser, between, task


class AskUser(HttpUser):
    wait_time = between(0.1, 0.3)

    @task
    def hit_async_ask(self) -> None:
        self.client.get("/async-ask", params={"q": "load-test"})
```

要点：

1. `HttpUser`：一个虚拟用户，自带会记统计的 `self.client`  
2. `@task`：用户循环执行的动作  
3. `wait_time`：两次任务之间的思考间隔（改成 `between(0, 0)` 压力更大）  

### 启动

```bash
uv run locust -f locustfile_async_ask.py --host http://127.0.0.1:8024
```

浏览器打开 **http://127.0.0.1:8089**，建议：

- Number of users：`10`  
- Spawn rate：`2`  
- Start，跑约 30～60 秒后 Stop  

在 Statistics 记下：**RPS**、**99%ile**、**Failures**。

### 实测参考（10 users，spawn 2）

| 指标 | 约值 |
|------|------|
| RPS（≈QPS） | **16.5** |
| 99%ile（≈P99） | **~410 ms** |
| Failures | **0%** |

单次 sleep 约 0.4s，P99≈0.4s 说明几乎没有排队恶化；RPS 由用户数与 wait_time 共同决定。

**为什么不是「10 用户 ÷ 0.2s wait ≈ 50 RPS」？**

`wait_time` 是在**一次 task 结束之后**才休息，接口本身还要先花约 **0.4s** 才返回。单个用户的一轮周期大约是：

```text
周期 ≈ 响应时间 + wait_time
     ≈ 0.4s + 0.2s（between(0.1,0.3) 的中位）
     ≈ 0.6s

理论上限 ≈ 用户数 ÷ 周期 ≈ 10 / 0.6 ≈ 16.7 RPS
```

与实测 **~16.5 RPS** 吻合。若把 `wait_time` 改成 `between(0, 0)`，周期≈0.4s，上限大约到 **25 RPS** 量级（仍受服务端与客户端调度影响，不会无限涨）。

---

## JMeter：最小压测

### 安装（官方包 + 本机 Java）

Homebrew 有时会卡在 JDK 依赖。可直接下官方二进制（国内可用清华镜像）：

```bash
mkdir -p .tools && cd .tools
curl -L -o jmeter.tgz \
  'https://mirrors.tuna.tsinghua.edu.cn/apache/jmeter/binaries/apache-jmeter-5.6.3.tgz'
tar -xzf jmeter.tgz && rm jmeter.tgz
./apache-jmeter-5.6.3/bin/jmeter -v   # 看到 5.6.3 即可
```

### 测试计划里有什么

一份最小 `.jmx` 通常包含：

| 组件 | 作用 |
|------|------|
| **Thread Group** | 线程数=用户数；Ramp-up=爬升秒数；Loop=每人循环次数 |
| **HTTP Request** | 协议/域名/端口/路径/方法（本文 `GET /async-ask`） |
| **Aggregate / Summary Report** | GUI 里看表；命令行则用 `-e -o` 出 HTML |

本文使用：`Threads=10`，`Ramp-up=5`，`Loops=20` → 共约 **200** 次请求，目标 `127.0.0.1:8024`。

**不想手搓 XML？** 用 GUI 大约 5 步也能配出同一计划（与下文 `.jmx` 等价）：

1. 启动：`./.tools/apache-jmeter-5.6.3/bin/jmeter`（无 `-n`，打开图形界面）  
2. 右键 Test Plan → Add → Threads → **Thread Group**：Number of Threads=`10`，Ramp-up=`5`，Loop Count=`20`  
3. 右键 Thread Group → Add → Sampler → **HTTP Request**：Server=`127.0.0.1`，Port=`8024`，Path=`/async-ask`，Method=`GET`，参数 `q=load-test`  
4. 右键 Thread Group → Add → Listener → **Aggregate Report**（或 Summary Report）  
5. 点绿三角 ▶ 跑完，在表里读 Throughput、99% Line、Error%  

配好后可 File → Save 成 `.jmx`，以后用命令行 `-n -t` 复跑。下面仍给出完整 XML，方便无 GUI 环境直接落盘。

把下面存为 `jmeter_async_ask.jmx`（完整可导入计划）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="async-ask" enabled="true">
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="Users" enabled="true">
        <stringProp name="ThreadGroup.num_threads">10</stringProp>
        <stringProp name="ThreadGroup.ramp_time">5</stringProp>
        <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <stringProp name="LoopController.loops">20</stringProp>
          <boolProp name="LoopController.continue_forever">false</boolProp>
        </elementProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="GET async-ask" enabled="true">
          <stringProp name="HTTPSampler.domain">127.0.0.1</stringProp>
          <stringProp name="HTTPSampler.port">8024</stringProp>
          <stringProp name="HTTPSampler.protocol">http</stringProp>
          <stringProp name="HTTPSampler.path">/async-ask</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
            <collectionProp name="Arguments.arguments">
              <elementProp name="q" elementType="HTTPArgument">
                <boolProp name="HTTPArgument.always_encode">false</boolProp>
                <stringProp name="Argument.name">q</stringProp>
                <stringProp name="Argument.value">load-test</stringProp>
                <stringProp name="Argument.metadata">=</stringProp>
              </elementProp>
            </collectionProp>
          </elementProp>
        </HTTPSamplerProxy>
        <hashTree/>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
```

### 命令行跑（推荐）

```bash
JMETER=./.tools/apache-jmeter-5.6.3/bin/jmeter
rm -rf jmeter-out results_async_ask.jtl
"$JMETER" -n -t jmeter_async_ask.jmx -l results_async_ask.jtl -e -o jmeter-out
```

终端里关注：

```text
summary =    200 in 00:00:13 =   15.9/s ... Err:     0 (0.00%)
```

- **`15.9/s`** → Throughput ≈ QPS  
- **`Err: 0`** → 失败率  
- **P99**：打开 `jmeter-out/index.html`，看 **99th pct**（控制台 summary 通常只印 Avg/Min/Max）

### 实测参考

| 指标 | 约值 |
|------|------|
| Throughput | **~15.9 /s** |
| 99th pct | **~408 ms** |
| Error% | **0%** |

与 Locust 同量级：同一服务、相近负载，两工具读数应接近（不必字节相等）。

---

## 优化前后对照

### Locust 打反例 `/async-block`

```python
"""Locust：打 /async-block（优化前反例）。"""

from __future__ import annotations

from locust import HttpUser, between, task


class BlockUser(HttpUser):
    wait_time = between(0.1, 0.3)

    @task
    def hit_async_block(self) -> None:
        self.client.get("/async-block", params={"q": "load-test"})
```

```bash
uv run locust -f locustfile_async_block.py --host http://127.0.0.1:8024
# Web UI 仍用 10 users / spawn 2，跑同样时长
```

### JMeter 对照

复制 ask 的 `.jmx`，把路径改成 `/async-block`（线程组参数不要改），例如：

```bash
sed 's/async-ask/async-block/g' jmeter_async_ask.jmx > jmeter_async_block.jmx
"$JMETER" -n -t jmeter_async_block.jmx -l results_async_block.jtl -e -o jmeter-out-block
```

### 实测对比（JMeter，同参数）

| 场景 | Throughput | P99 | Error |
|------|------------|-----|-------|
| **优化后** `/async-ask` | **~16 /s** | **~0.4 s** | 0% |
| **优化前** `/async-block` | **~2.5 /s** | **~5.3 s** | 0% |

**读数：**

- `await` 不堵 loop → 10 个用户能重叠等待 → QPS 高、P99 贴近单次 0.4s  
- `time.sleep` 堵 loop → 近似串行 → QPS 掉一个数量级，P99 飙到数秒  

**资源旁白（别误读成「CPU 被 sleep 打满」）：**

`time.sleep` 会让线程**挂起等待**，通常**不会**像忙等循环那样把 CPU 打满；任务管理器里 CPU 往往看起来并不「很忙」，但 **QPS 已经塌了**。瓶颈不是「算力不够」，而是 **唯一的事件循环线程被卡住，别的请求无法被调度**——机器闲着，吞吐却上不去。

对比记忆：

| | `await asyncio.sleep` | `time.sleep`（在 async 路由里） | 忙等 `while time.time() < …` |
|--|----------------------|--------------------------------|------------------------------|
| 事件循环 | 可调度别人 | **堵住** | **堵住** |
| CPU | 低（在等） | 往往也低（在睡） | **飙高（空转）** |
| 本文反例 | `/async-ask` | `/async-block` | 本文未演示 |

所以优化的收益是立体的：**不是把 CPU 从 100% 降下来，而是把「闲着却串行」变成「等待时可并发」。**

口诀：**对照时锁死用户数、爬升、时长/循环、工具、机器与请求内容；只改要验证的那一处。**

---

## 第 4 周收官地图

```text
画像     先找到慢在哪（CPU 忙 vs 在等）
  ↓
缓存     相同问句少干活（Redis）
  ↓
异步     等待时不堵别人（真 await，别在 async 里 sleep）
  ↓
批处理   客户端一次干一捆（embed / rerank）
  ↓
引擎     推理算力侧更快（如 vLLM continuous batching）
  ↓
压测     Locust / JMeter：QPS + P99 + 失败率  ← 本文
```

压测不替代前面任何一刀；它回答「改完之后，在压力下是否真的更好」。

---

## 新手向坑

### 1. 只看 QPS，不看 P99 / 失败率

- **现象**：Throughput 很高，用户仍投诉「偶发卡死」  
- **原因**：尾部延迟与错误被平均吞吐掩盖  
- **处理**：报告固定读三件套：**Error% → QPS → P99**

### 2. 对照时条件乱变

- **现象**：一边 10 用户、一边 50 用户，或一边有缓存一边没有  
- **原因**：变量太多，无法归因  
- **处理**：只改路径或只改代码分支；用户数、Ramp-up、循环、工具对齐

### 3. JMeter 终端里找不到 P99

- **现象**：summary 只有 Avg/Min/Max  
- **原因**：命令行 summariser 默认不打印百分位  
- **处理**：加 `-e -o 报告目录`，打开 HTML；或 GUI 看 Aggregate Report

### 4. Locust / JMeter 警告刷屏

- **现象**：`Unsafe`、`package scanning`、`sun.awt.X11` 等 WARNING  
- **原因**：Java 版本与依赖的兼容提示，本练习可忽略  
- **处理**：以 `summary =` / Web UI 数字为准；真正失败看 Error% 与连接拒绝

---

## 本文 deliberately 没做什么

- 没用 Grafana / Prometheus 做实时大盘（属可观测性专题）  
- 没做多机分布式压测、没证明「QPS 一定 ×10」  
- 没对真实大模型端口做满负荷压测（成本高；本文用 0.4s sleep 模拟 I/O）  
- 没展开 JMeter 全部协议与插件  

---

## 小结

| 问题 | 答案 |
|------|------|
| QPS vs P99？ | QPS=单位时间产能；P99=最惨 1% 等多久。只盯 QPS 会漏尾部与失败 |
| Locust vs JMeter？ | 同一类指标；Python 脚本 vs GUI/`.jmx`。今天两者都会：起服务 → 加压 → 读吞吐与 P99 |
| 优化前后怎么比？ | 锁死负载与环境，只改一点；本文 ask≈16/s·0.4s vs block≈2.5/s·5s |
| 压测在第 4 周哪一环？ | 收官验收：前面怎么优化，这里用数字说话 |
