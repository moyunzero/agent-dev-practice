# 用 vLLM-Metal 部署开源模型并测吞吐：墙钟、req/s、token/s 怎么读

Agent 里「慢」不只有网络：大模型**每生成一个字**都要算。  
换更快的**推理引擎**（inference engine），让 GPU/Metal 一次干更多活——这是 **vLLM** 一类工具的主战场。

本文在 **Apple Silicon（M 系列 Mac）** 上走官方 **vLLM-Metal** 路径：起一个 OpenAI 兼容的本地服务，用 `curl` 验收，再用小脚本对比 **串行 8 请求** vs **并发 8 请求** 的吞吐。  
文中会把 **墙钟时间（wall）**、**req/s**、**completion_tok/s** 等名词讲清楚——读完后你应能独立解释测出来的每一行数字。

## 你将会得到什么

1. 说清 vLLM 优化的是**推理算力侧**，和 Redis 缓存各管什么  
2. 在本机用 vLLM-Metal 起 `vllm serve`，并用 `curl` 打出 chat 回复  
3. 读懂吞吐脚本输出的 **wall / req/s / completion_tok/s**  
4. 区分 **continuous batching（服务端动态组批）** 和 **客户端事先 embed 一批**  

---

## 零基础名词表

> 建议先读完本节再动手。每个词都按：**是什么 → 在本文干什么 → 怎么区分** 来写。

### 大模型推理（Inference）

| 层 | 说明 |
|----|------|
| **是什么** | 模型已经训练好，你现在让它**根据输入生成输出**（聊天、补全），这叫推理，不是训练 |
| **在本文干什么** | 我们要部署一个能对外接 HTTP 请求的推理服务，而不是在 Python 里 `model.generate()` 玩一下 |
| **怎么区分** | **训练**改权重；**推理**用固定权重算答案。Agent 在线问答几乎全是推理 |

### vLLM

| 层 | 说明 |
|----|------|
| **是什么** | 一个开源的**大模型推理引擎 + 服务框架**，主打高吞吐：PagedAttention、continuous batching 等 |
| **在本文干什么** | 用 `vllm serve` 在本地 `:8027` 起一个服务，对外提供和 OpenAI 很像的 HTTP API |
| **怎么区分** | 它不是「又一个聊天 App」，而是**替你把模型跑快、跑满算力**的服务端组件。和 Ollama 同类，但实现和指标侧重不同（下文有对照） |

### vLLM-Metal / MLX / Apple Metal

| 层 | 说明 |
|----|------|
| **是什么** | **vLLM-Metal** 是 vLLM 在 Apple Silicon 上的插件，底层走 **MLX** 框架，算力走 Mac 的 **Metal** GPU |
| **在本文干什么** | M 系列 Mac **没有 NVIDIA CUDA**，不能 `pip install vllm` 装官方 CUDA 版；必须装 **vLLM core + vllm_metal 插件** |
| **怎么区分** | **CUDA 版 vLLM**：Linux/Windows + NVIDIA 显卡。**vLLM-Metal**：Mac arm64。**Ollama**：另一套本地推理，安装更简单，本文用它作「也有本地推理」的对照，不测谁绝对更快 |

### OpenAI 兼容 API

| 层 | 说明 |
|----|------|
| **是什么** | HTTP 路径和 JSON 字段设计成和 OpenAI 很像，例如 `POST /v1/chat/completions` |
| **在本文干什么** | 用 `curl` 或任意 HTTP 客户端就能测，不必绑死某个 SDK |
| **怎么区分** | **兼容**≠完全一样；字段名大体相同，细节以 `vllm serve --help` 和返回 JSON 为准 |

### Token（词元）

| 层 | 说明 |
|----|------|
| **是什么** | 模型处理文本的最小单位，不是「一个字」：中文往往多个字合一个 token，英文一个词可能是 1～几个 token |
| **在本文干什么** | 响应 JSON 里的 `usage.prompt_tokens` = 输入算了多少 token；`usage.completion_tokens` = **模型生成了多少 token** |
| **怎么区分** | **字符数**和 **token 数**不是 1:1。比速度时 industry 更常用 **token/s**，因为和模型内部计算步数对齐 |

### 墙钟时间（wall / wall clock time）

| 层 | 说明 |
|----|------|
| **是什么** | 用你手腕上的表量的时间：从**开始发第一个请求**到**最后一个响应收齐**一共过了多少秒 |
| **在本文干什么** | 脚本里 `wall=13.53s` 表示「这一组 8 个请求总共花了 13.53 秒」 |
| **怎么区分** | **单请求耗时**：每个请求各自 `elapsed`（可能 1～2 秒）。**墙钟**：整组任务的日历时间。并发时墙钟往往**远小于** 8 倍单请求耗时，因为多个请求在重叠进行 |

```text
串行 8 请求：  [====req1====][====req2====]…  wall ≈ 8 × 单次
并发 8 请求：  [====req1====]
               [====req2====]  重叠进行
               …               wall ≈ 最慢那条附近，明显更短
```

### 吞吐量（Throughput）与 req/s

| 层 | 说明 |
|----|------|
| **是什么** | **吞吐** = 单位时间里完成了多少活。**req/s** = 每秒完成的 **HTTP 请求个数**（requests per second） |
| **在本文干什么** | 脚本打印 `0.59 req/s` vs `2.59 req/s`：并发时每秒完成的请求数更高 |
| **怎么区分** | **延迟（latency）**：一个用户发一问，多久拿到答案。**吞吐**：很多请求堆在一起，系统每秒能清多少单。优化吞吐不一定降低「这一问」的延迟 |

### completion_tok/s（生成 token 每秒）

| 层 | 说明 |
|----|------|
| **是什么** | 把这一组请求里所有 **`completion_tokens` 加起来**，除以墙钟秒数，得到**生成侧**每秒产出多少 token |
| **在本文干什么** | 本文实测：串行 **22.1 completion_tok/s**，并发 **106.3 completion_tok/s**——更能反映引擎「写字」有多快 |
| **怎么区分** | **req/s** 受「每个回答长短」影响（回答越长，同样 req/s 下 token 更多）。**completion_tok/s** 更贴近 GPU/Metal 算力利用率。读 vLLM 类 benchmark 时，**tok/s 比 req/s 更常出现** |

计算公式（与脚本一致）：

```text
req/s              = 请求个数 N ÷ wall（秒）
completion_tok/s   = 所有响应的 completion_tokens 之和 ÷ wall（秒）
```

### 串行（sequential）vs 并发（concurrent）

| 层 | 说明 |
|----|------|
| **是什么** | **串行**：第 2 个请求等第 1 个完全返回再发。**并发**：多个请求几乎同时发出，在服务端重叠处理 |
| **在本文干什么** | `measure_throughput.py` 先跑串行 8 次，再跑 8 线程各发 1 次，对比 wall 和 req/s |
| **怎么区分** | 并发**不是**把 8 个问题拼成一条 HTTP（那是客户端组批）；这里是 **8 条独立 HTTP**，靠服务端 **continuous batching** 吃并发 |

### Continuous batching（连续批处理）

| 层 | 说明 |
|----|------|
| **是什么** | 推理引擎在服务端把**同时在进行的多条生成请求**动态拼进同一批 GPU/Metal 计算；某条先生完可以先离开，新请求可以插进来——批是「活的」 |
| **在本文干什么** | 解释为什么并发 8 请求时 wall 从 ~13.5s 降到 ~3.1s：引擎没有傻等「一条做完再做下一条」 |
| **怎么区分** | 见下节与 **客户端静态批** 的对照 |

### PagedAttention（分页注意力，知道即可）

| 层 | 说明 |
|----|------|
| **是什么** | vLLM 用来**更省显存地存 KV cache** 的技术，让更多并发序列能同时跑 |
| **在本文干什么** | 你不需要手改代码；日志里可能出现 `Paged attention enabled`，知道是「为了多路并发更省内存」即可 |
| **怎么区分** | 和 **continuous batching** 是不同刀法：PagedAttention 偏内存/KV；continuous batching 偏调度/拼批 |

### 客户端静态批 vs 服务端 continuous batching

| | 客户端静态批（如 embed 一批） | 服务端 continuous batching |
|--|-------------------------------|----------------------------|
| **谁组批** | 你的代码先把列表凑齐 | vLLM 收到多路 HTTP 后自己拼 |
| **批何时定** | 发请求前就定好 `[chunk1…chunkN]` | 请求长短不一，随时进/出 |
| **典型场景** | 离线建库：手里已有一捆 chunk | 在线：多用户同时 chat |
| **本文** | 不演示 embed；只作概念对照 | 并发 8 路 `/v1/chat/completions` |

```text
Day26 思路：  客户端 ──[文1,文2,文3]──► 一次 embed ──► 多个向量
Day27 思路：  客户端 ──8 条独立 HTTP──► vLLM 内部动态拼批 ──► 8 份回复
```

### vLLM vs Redis 缓存 vs 异步 vs 客户端批处理

| | 解决什么 | 前提 |
|--|----------|------|
| **Redis 缓存** | 相同问句**少算** | 问句/key 会重复 |
| **异步（async）** | 等待 I/O 时不阻塞线程 | 多请求同时在等 |
| **客户端批** | 一次调用算多条固定输入 | 已攒齐一捆数据 |
| **vLLM 引擎** | **每次推理本身更快、并发更高** | 已部署推理服务 |

四者可以叠加：缓存减少重复；vLLM 让每次生成更快；异步让 Web 层不堵；客户端批适合离线 embed。

### 架构：本文最小流水线

```text
你（curl / Python）
    │  HTTP POST /v1/chat/completions
    ▼
vLLM API Server (:8027)
    │  调度、continuous batching
    ▼
EngineCore + MLX on Metal
    │  加载 mlx-community/Qwen2.5-0.5B-Instruct-4bit
    ▼
JSON 响应（choices[].message.content + usage）
```

---

## 环境准备

- **机器**：Apple Silicon（arm64），本文在 M4 Mac 上验证  
- **Python**：3.12（安装脚本会用 `uv` 建独立虚拟环境）  
- **磁盘**：首次 `vllm serve` 会从 Hugging Face 下载约 **278MB** 模型权重  
- **网络**：安装 vllm_metal 插件时要下 GitHub Release 的 wheel；国内直连 GitHub 可能超时（见下文坑）  

确认架构：

```bash
python3.12 -c 'import platform; print(platform.machine(), platform.python_version())'
# 期望：arm64 3.12.x
```

---

## 安装 vLLM-Metal

官方一键脚本（会装 vLLM core + 尝试下 vllm_metal wheel）：

```bash
curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
```

默认虚拟环境：`~/.venv-vllm-metal`

**装好了怎么确认：**

```bash
source ~/.venv-vllm-metal/bin/activate
python -c "import vllm; import vllm_metal; print('vllm', vllm.__version__)"
# 能 import 且无报错即可
```

若脚本在 `Downloading wheel...` 处 **`curl: (56) Operation timed out`**：core 可能已装好，只是 **metal 插件 wheel 没下完**。可手动用镜像拉 wheel 再装（文件名以 release 为准）：

```bash
curl -L -o /tmp/vllm_metal.whl \
  'https://ghfast.top/https://github.com/vllm-project/vllm-metal/releases/download/v0.28.0.dev20260901094532/vllm_metal-0.28.0.dev20260901094532-cp312-cp312-macosx_15_0_arm64.whl'

source ~/.venv-vllm-metal/bin/activate
uv pip install /tmp/vllm_metal.whl
```

---

## 启动服务

**终端 A**（保持运行，不要关）：

```bash
source ~/.venv-vllm-metal/bin/activate
vllm serve mlx-community/Qwen2.5-0.5B-Instruct-4bit --port 8027
```

**第一次启动**通常要 3～5 分钟：下权重 → 加载 MLX → KV cache → warmup。  
日志里出现下面两行，表示可以接客了：

```text
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8027
```

常见可忽略警告：

- `Triton not installed` — Mac Metal 路径正常  
- `ulimit of 2048` — 本练习请求数少，一般无碍  
- `unauthenticated requests to the HF Hub` — 未设 `HF_TOKEN` 也能下，可能稍慢  

---

## 用 curl 验收（终端 B）

**1. 看模型是否在列表里**

```bash
curl -s http://127.0.0.1:8027/v1/models | head -c 500
echo
```

期望 JSON 里出现 `"id":"mlx-community/Qwen2.5-0.5B-Instruct-4bit"`。

**2. 打一条 chat**

```bash
curl -s http://127.0.0.1:8027/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "messages": [{"role": "user", "content": "用一句话介绍 vLLM"}],
    "max_tokens": 64
  }'
```

**成功长什么样：** JSON 里有 `"choices":[{"message":{"role":"assistant","content":"……"}}]`，且 `content` 非空。  
小模型可能胡说——验收看**接口通**，不看答案质量。

---

## 测吞吐：串行 vs 并发

新建 `measure_throughput.py`（**先确保终端 A 的 `vllm serve` 仍在跑**）：

```python
"""对比串行 vs 并发请求的吞吐（需先 vllm serve :8027）。"""

from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "http://127.0.0.1:8027/v1/chat/completions"
MODEL = "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
N = 8
MAX_TOKENS = 64


def one_request(i: int) -> tuple[float, int, int]:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": f"用不超过二十个字回答：什么是批处理？编号{i}",
                }
            ],
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    elapsed = time.perf_counter() - t0
    usage = data.get("usage") or {}
    return elapsed, int(usage.get("completion_tokens") or 0), int(
        usage.get("prompt_tokens") or 0
    )


def summarize(label: str, wall: float, rows: list[tuple[float, int, int]]) -> None:
    out_tok = sum(r[1] for r in rows)
    req_s = len(rows) / wall if wall > 0 else 0.0
    tok_s = out_tok / wall if wall > 0 else 0.0
    print(f"\n=== {label} ===")
    print(f"requests={len(rows)}  wall={wall:.2f}s")
    print(f"completion_tokens={out_tok}")
    print(f"throughput: {req_s:.2f} req/s  |  {tok_s:.1f} completion_tok/s")


def main() -> None:
    print(f"POST {URL}  N={N}  max_tokens={MAX_TOKENS}")

    seq_rows: list[tuple[float, int, int]] = []
    t0 = time.perf_counter()
    for i in range(N):
        seq_rows.append(one_request(i))
    summarize("sequential (one-by-one)", time.perf_counter() - t0, seq_rows)

    conc_rows: list[tuple[float, int, int]] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N) as pool:
        futs = [pool.submit(one_request, i) for i in range(N)]
        for fut in as_completed(futs):
            conc_rows.append(fut.result())
    summarize(f"concurrent (workers={N})", time.perf_counter() - t0, conc_rows)

    print(
        "\n读数要点：wall 变短 + req/s 升高 → 引擎在用 continuous batching 吃并发；"
        "completion_tok/s 才是生成侧吞吐。"
    )


if __name__ == "__main__":
    main()
```

运行：

```bash
python3 measure_throughput.py
```

### 实测结果（M4 Mac，供对照）

```text
=== sequential (one-by-one) ===
requests=8  wall=13.53s
completion_tokens=299
throughput: 0.59 req/s  |  22.1 completion_tok/s

=== concurrent (workers=8) ===
requests=8  wall=3.09s
completion_tokens=329
throughput: 2.59 req/s  |  106.3 completion_tok/s
```

### 怎么读这几行

| 字段 | 含义 | 本例 |
|------|------|------|
| `wall` | 这一组 8 请求的总墙钟秒数 | 13.53 → 3.09，约 **4.4×** 加速 |
| `completion_tokens` | 8 条回复一共生成了多少 token | 299 vs 329（略不同正常：模型生成长度不完全固定） |
| `req/s` | 8 ÷ wall | 0.59 → 2.59 |
| `completion_tok/s` | completion_tokens 之和 ÷ wall | 22.1 → **106.3** |

**结论（人话）：**

- 并发并没有把 8 个问题合成 1 个 HTTP；是 **8 路同时到 vLLM**，引擎用 **continuous batching** 重叠算力。  
- **单条请求的延迟**不会 magically 变成原来的 1/8；变短的是 **「8 条全部完成」的总时间**。  
- 看引擎「写字」有多快，优先盯 **completion_tok/s**。

---

## 新手向坑

### 1. 安装脚本下 wheel 超时

- **现象**：`curl: (56) Recv failure: Operation timed out`，`Failed to download wheel`  
- **原因**：vllm_metal 的 `.whl` 在 GitHub Releases，国内网络常慢  
- **处理**：用镜像 URL 手动 `curl` 再 `uv pip install`（见上文安装节）

### 2. `vllm serve` 起很久像卡死

- **现象**：只有 `Platform plugin metal is activated`，几分钟没端口  
- **原因**：首次下载 ~278MB 权重 + MLX 加载 + warmup  
- **处理**：看日志是否有 `Download complete` / `MLX-LM model loaded` / `Application startup complete`；另开终端 `curl http://127.0.0.1:8027/v1/models`

### 3. 把 req/s 当「单用户体感速度」

- **现象**：并发 req/s 很高，但自己只发一问仍觉得慢  
- **原因**：吞吐优化的是**多路叠加**时的总产能；单问延迟还受 prompt 长度、生成长度、首 token 时间影响  
- **处理**：单用户体验看 **latency**；系统容量看 **tok/s / req/s**

---

## 本文 deliberately 没做什么

- 没用 **NVIDIA CUDA 版 vLLM**（本文机器是 Mac）  
- 没用 **Llama 3 全尺寸**（改用 **mlx-community 小模型** 降低内存与下载时间）  
- 没用 **Locust / wrk** 做压测（Day28 专题；本文用 8 路并发理解概念）  
- 没展开 **量化算法、多卡、SGLang/TRT** 实装  
- 没和 Ollama 做同条件 benchmark（仅作「本地推理还有这条路线」的对照）

---

## 收工

```bash
# 终端 A：Ctrl+C 停 vllm serve
# 可选：删除大 venv（确认不再需要再删）
# rm -rf ~/.venv-vllm-metal
```

---

## 小结

| 问题 | 答案 |
|------|------|
| vLLM 相对 Redis 优化什么？ | **推理算力侧**：同样要算时算得更快、并发更高；缓存是少算 |
| continuous batching vs 客户端 embed 一批？ | 前者 **服务端动态** 吃多路 HTTP；后者 **客户端静态** 凑列表一次调用 |
| Mac 为何用 vLLM-Metal？ | 无 CUDA；Metal + MLX 才是 Apple Silicon 上的官方支持路径 |
| wall / req/s / completion_tok/s？ | 总秒数 / 每秒请求数 / 每秒生成 token 数——读 benchmark 的三件套 |
