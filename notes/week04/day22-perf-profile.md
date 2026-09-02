# 用 cProfile 和 py-spy 分析现有 Agent 的性能瓶颈

系统慢，第一反应不该是「加缓存、上异步、换引擎」——**先量清楚慢在哪**。  
本文教你用 **`cProfile`** 和 **`py-spy`**，给带工具的 Agent 做性能画像：慢在本地狂算，还是在等大模型。

阅读路径分两步（都建议做完）：

1. **热身**：故意变慢的小流水线，学会读 `tottime`，分清「CPU 忙」与「在等待」  
2. **实战**：对真实 Agent（`create_agent` + 工具 + Ollama）跑 cProfile，并对运行中进程用 py-spy 采样——你会看到墙钟时间多半花在「等模型」，而不是本地小工具  

## 你将会得到什么

1. 会用 cProfile 读 `tottime` / `cumtime`  
2. 分清 CPU 忙 vs 等待，且知道优化方向不同  
3. 对真实 Agent 出表：常见热点是 `socket.recv` / HTTP 读，而不是本地 `@tool`  
4. 会用 py-spy 对**真实数字 PID**采样（macOS 可能需要 `sudo`）  

---

## 零基础名词表

> 建议先读完再动手。

### 性能瓶颈

| 层 | 说明 |
|----|------|
| **是什么** | 限制整体变快的那一段 |
| **在本文干什么** | 判断慢在「狂算」还是「干等模型」 |
| **怎么区分** | 墙钟慢 ≠ CPU 一定打满 |

### CPU 忙 vs 在等待

| 类型 | 类比 | 小流水线例子 | 真实 Agent 例子 | 优化方向（概念） |
|------|------|--------------|-----------------|------------------|
| **CPU 忙** | 厨师狂切菜 | `fake_retrieve` 哈希 | 少见（本地工具通常很快） | 少算、更好算法 |
| **在等待** | 菜进烤箱 | `time.sleep` | `socket.recv` / `httpcore.read` 等 Ollama | 更快推理、少调模型、缓存 |

### cProfile（Python 自带的「函数计时器」）

| 层 | 说明 |
|----|------|
| **是什么** | Python **标准库**里的性能分析器（`import cProfile`），用来回答：「这段程序跑完后，**每个函数分别花了多少时间？**」不用额外 `pip install`。 |
| **在本文干什么** | 热身：包住小流水线 `run_agent_pipeline`；实战：包住真实 `run_agent`。跑完打印按耗时排序的表，找出慢函数名。 |
| **怎么区分** | 它量的是**你这次运行里调用到的 Python 函数**；不是操作系统级「哪个进程占 CPU」的总览工具（那是 top/Activity Monitor）。 |

**它怎么工作（直觉）：**

1. 你在代码里 `profiler.enable()`，像按下「开始计时」  
2. 中间照常跑业务（小流水线或 Agent）  
3. `profiler.disable()` 后，它交出一张表：每个函数被调用几次、自己花了多久、连同子函数一共多久  

类比：给厨房里**每一个工种**发考勤打卡机——切菜、焯水、装盘各记各的工时；下工后汇总「谁加班最多」。

**你要会看的几列：**

| 列名 | 人话 |
|------|------|
| `ncalls` | 这个函数被叫了多少次 |
| `tottime` | **它自己**干活的时间（不含它叫出去的子函数） |
| `cumtime` | **它 + 它手下整条链**一共多久 |
| 最后一列 | 函数在哪个文件、哪一行 |

**擅长 / 不擅长：**

| 擅长 | 不擅长 / 注意 |
|------|----------------|
| 本地开发时精确定位「哪个函数慢」 | 必须改代码（或用命令行包一层）才能开表 |
| 区分「自己在算」还是「自己在 sleep/recv」 | 对**已经在跑、你改不了代码**的进程不方便 |
| 标准库，环境干净 | 计时本身有一点点开销；表会很长，要会排序看 Top |

**和命令的关系：** `step01_cprofile.py` / `step03_cprofile_agent.py` 就是在代码里打开 cProfile，再 `pstats` 按 `tottime` 或 `cumtime` 打印前几名。

### tottime 与 cumtime（读 cProfile 表的两把尺子）

| 列 | 含义 | 怎么用 |
|----|------|--------|
| **tottime** | 自身耗时，不含子调用 | 找「谁自己在忙/在等」（如 `recv`、`time.sleep`、哈希 `digest`） |
| **cumtime** | 含子集累计 | 看整条链（如 `run_agent` → `chat_models.invoke`）谁拖时间 |

分析 Agent 时：常先扫 **cumtime** 是否堆在模型/HTTP，再看 **tottime** 是否是 `recv` 一类等待。  
反例：某个包装函数 `cumtime` 很大但 `tottime` 接近 0，说明它自己没干活，慢在它调用的下游。

### py-spy（站在进程外面的「巡场抽查」）

| 层 | 说明 |
|----|------|
| **是什么** | 一个**独立的命令行工具**（本文用 `uv` 安装的 `py-spy`），用来回答：「**正在运行的**那个 Python 进程，*此刻* 多半卡在哪一行 / 哪层调用栈？」 |
| **在本文干什么** | 对 `step04_pyspy_agent_target.py` 打印出的 **PID** 执行 `py-spy top`（或 `record` 出火焰图），在 Agent 循环跑的时候从外部采样。 |
| **怎么区分** | 一般**不用改**业务代码；盯的是「别的终端里已经起来的进程」。它和 cProfile 不是同一个软件：一个是库打进你的脚本，一个是外面的探头。 |

**它怎么工作（直觉）：**

1. 目标程序自己在跑（例如 step04 循环调 Agent）  
2. py-spy 知道进程号 PID 后，**每隔很短时间偷看一眼**：CPU 现在停在哪个函数  
3. 偷看很多次后统计：「出现在 `httpcore.read` 的次数特别多」→ 说明经常卡在读网络  

类比：你不进厨房改菜谱，只在门口**每秒推门看一眼**——十次有九次看见人盯着烤箱，就知道瓶颈是「在等」，不是「在切菜」。

**常见子命令：**

| 命令 | 作用 |
|------|------|
| `py-spy top --pid 数字` | 实时刷新「谁最烫」的排行（本文主用） |
| `py-spy record -o xxx.svg --pid 数字` | 采一段时间，生成火焰图，用浏览器打开 |

**擅长 / 不擅长：**

| 擅长 | 不擅长 / 注意 |
|------|----------------|
| 不改代码也能看正在跑的服务 | 得到的是**采样统计**，不是像 cProfile 那样每次调用都精确计时 |
| 生产/演示机上临时排查 | macOS 常要权限（`requires root` → 可 `sudo`） |
| 和 cProfile 交叉验证（都指向等模型） | 文档里的 `<PID>` 是占位符，必须换成真实数字，否则 zsh 会报错 |

**和命令的关系：**

```bash
# 终端 A 打印 PID=35969 之后：
uv run py-spy top --pid 35969
# macOS 若提示 requires root：
sudo uv run py-spy top --pid 35969
```

成功时常见：`read (httpcore/…)`、`_generate (langchain_ollama/…)` —— 与 cProfile 里的 `socket.recv` 互相印证「在等模型」。

### cProfile vs py-spy（一张表记牢）

| | **cProfile** | **py-spy** |
|--|--------------|------------|
| 身份 | Python 标准库 | 外部 CLI 工具 |
| 何时看 | 通常跑**完**再出表 | 进程**正跑**时采样 |
| 是否改代码 | 常常要（enable/disable） | 通常不要 |
| 结果形态 | 函数耗时表（tottime/cumtime） | top 排行 / 火焰图 |
| 本文示例脚本 | step01 / step03 | step04 + `py-spy top --pid …` |
| 类比 | 下班后看全员工时表 | 巡场抽查「现在谁在干嘛」 |

两者互补：cProfile 适合「精确到函数的账本」；py-spy 适合「不动代码、盯着活进程」。分析真实 Agent 时，最好两个都试；macOS 上 py-spy 没权限时，仍可用 cProfile 定性。

### 现有 Agent（本文实战对象）

| 层 | 说明 |
|----|------|
| **是什么** | `create_agent` + `@tool` + 本地 Ollama，典型的「带工具 Agent」 |
| **在本文干什么** | `real_agent.py` / `step03` / `step04` |
| **怎么区分** | 与前面的 `workload.py` 小流水线不同：这里会真的调模型；小流水线只负责练读表 |

```text
用户问题
  → Agent 多次调用 Ollama（决定工具 / 写答案）
  → 本地 get_word_length / add（通常极快）
墙钟大头：等 Ollama（网络 recv / http 读）
```

### Scalene（了解即可）

更丰富的 CPU/内存画像；本文不展开安装与实操。

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- 热身：可不启模型  
- 实战 Agent：本机 [Ollama](https://ollama.com/) + `qwen2:7b`（或你设置的 `OLLAMA_MODEL`）  

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day22-perf-profile && cd day22-perf-profile
```

### `pyproject.toml`

```toml
[project]
name = "day22-perf-profile"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "langchain>=1.0",
  "langchain-ollama>=0.3",
  "langgraph>=0.2",
  "py-spy>=0.4.0",
]
```

```bash
uv sync
```

---

## 第 1 步：热身（小流水线练读表）

`workload.py`：`fake_retrieve`（CPU）→ `fake_embed`/`fake_llm`（`sleep`）。

```bash
uv run python step01_cprofile.py
```

学会：按 `tottime` 排序；哈希 = 忙算；`time.sleep` = 等待。  
读表手感有了之后，进入下一步：给**真会调模型的 Agent**画像——小流水线里的「慢」和真 Agent 的「慢」往往不是同一类。

---

## 第 2 步：实战——分析现有 Agent

### `real_agent.py`（核心）

```python
from langchain.agents import create_agent
from langchain.tools import tool

@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)

@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b

def run_agent(question: str) -> str:
    agent = create_agent(
        model="ollama:qwen2:7b",
        tools=[get_word_length, add],
        system_prompt="需要长度或加法必须调工具；先长度再 add。",
    )
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    # 取最后一条无 tool_calls 的 AIMessage …
```

### cProfile

```bash
uv run python step03_cprofile_agent.py
```

期望现象（示例量级因机器而异）：

- Answer 合理（如字母数+10）  
- **tottime** 顶部常见 `{method 'recv' of '_socket.socket'}`  
- **cumtime** 堆在 `chat_models` / `model_node`  
- 几乎看不到 `get_word_length` / `add`  

结论：**瓶颈是等待模型，不是本地工具 CPU。**

### py-spy

终端 A：

```bash
uv run python step04_pyspy_agent_target.py
# 例如：PID=35969
```

终端 B（换成你的数字；不要写 `<PID>`）：

```bash
uv run py-spy top --pid 35969
# macOS 若提示 requires root：
sudo uv run py-spy top --pid 35969
```

成功时常见：`read (httpcore/…)`、`_generate (langchain_ollama/…)`、`model_node` —— 与 cProfile 互相印证。

---

## 新手向坑

| 现象 | 原因 | 处理 |
|------|------|------|
| `zsh: parse error` 且命令含 `<PID>` | 把文档占位符原样粘贴了 | 换成进程打印的真实数字，去掉尖括号 |
| `requires root on OSX` | macOS 对附加调试的限制 | `sudo uv run py-spy …`，或先用 cProfile 定性 |
| 想优化本地 `add` 让 Agent 明显变快 | 报表显示时间几乎都在等模型 | 优先：更快推理引擎、少轮模型调用、缓存等 |
| 只看小流水线就推断真 Agent 瓶颈 | 假 sleep/哈希 ≠ 真 Ollama 等待 | 再跑 step03 / step04，对照 `recv` / `httpcore.read` |

---

## 边界：做了什么 / 故意没做什么

**做了**

- cProfile + py-spy 的用法与读表  
- 用小流水线练「忙算 vs 等待」，再用真实 Agent 看「等模型」  
- 交叉印证：cProfile 的 `socket.recv` 与 py-spy 的 `httpcore.read` / Ollama `_generate`  

**故意没做**

- Redis 缓存、异步改造、批处理、vLLM 部署（那是优化手段，本文只做画像）  
- Scalene 实操  
- 更大的「RAG + 网页搜索」研究助手全链路压测（方法相同，可自行套用）  

---

## 一句话收束

**先画像再下药：用小例子学会读表，再用 cProfile / py-spy 给真实 Agent 体检；多数时候你会发现瓶颈在「等模型」，而不是本地那两行工具代码。**
