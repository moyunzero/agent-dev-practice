# 用 LangSmith 追踪 Agent 调用链：从环境变量到 Trace 树排障

Agent 一次问答往往要经过 **模型推理 → 选工具 → 调工具 → 再推理**。终端里几行 `print` 只能看到片段，很难回答：

> 总共 8 秒，慢在 LLM 还是 RAG？工具有没有真的跑起来？参数传错发生在哪一步？

**LangSmith** 是 LangChain 生态的链路追踪服务：不改业务逻辑，只靠环境变量把每次 Run 的结构、耗时、输入输出送到 Web UI，用 **Trace 树** 一眼定位瓶颈。

本文把 LangSmith 接到本地 **Ollama + LangChain Agent**，跑通一次问答，并在 UI 里读懂「模型慢 / 检索慢 / 参数格式错」分别长什么样。

## 你将会得到什么

1. 用人话区分 **Trace、Run、Span**，以及它们和 `print` 日志的差别  
2. 用 **三个环境变量** 打开 LangSmith，**零改 Agent 代码** 也能出完整 trace  
3. 在 LangSmith 项目页打开一次 Run，能指着树讲清：哪一步最慢、工具是否执行、报错类型  
4. 认识一个常见坑：小模型 **tool call 参数格式** 不对，Trace 里会在 tool 节点看到 validation error  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### 可观测性（Observability）与链路追踪（Tracing）

| 层 | 说明 |
|----|------|
| **是什么** | 可观测性 = 用日志、指标、追踪等手段，从外部理解系统内部发生了什么。链路追踪专门记录**一次请求经过的每个步骤**及父子关系 |
| **在本文干什么** | Agent 问答不是「黑盒一次返回」；LangSmith 把模型调用、工具调用拆成树，方便排障 |
| **怎么区分** | **指标**（如 QPS、P99）看整体趋势；**追踪**看**单次请求**里每一步。本文聚焦追踪，不展开 Prometheus（下一篇常见主题） |

```text
用户一问 ──► Agent（LangGraph / create_agent）
                 ├── Run: 模型第 1 轮（~4s）
                 ├── Run: search_knowledge_base（成功则 ~0.x–2s；失败则红叉）
                 └── Run: 模型第 2 轮（~4s）
                         └── Trace 总耗时 ≈ 各步之和（有重叠时 UI 会标注）
```

### Trace（一次完整追踪）

| 层 | 说明 |
|----|------|
| **是什么** | 对应**一次端到端任务**（例如用户一个问题），下面挂着所有子步骤 |
| **在本文干什么** | LangSmith 项目列表里每一行 Run，点进去看到的**整棵树**就是这次 Trace |
| **怎么区分** | Trace = 整次问答；树里的**每一个节点**是 Run/Span。不要和「一次 HTTP 请求」混为一谈——Agent 内部可能多次调模型 |

### Run / Span（树上的节点）

| 层 | 说明 |
|----|------|
| **是什么** | **Run** 是 LangSmith 里的一步执行记录（模型、链、工具各算一步）。**Span** 在 OpenTelemetry 里常用；LangSmith UI 里你主要看到 **Run** 及耗时 |
| **在本文干什么** | 看节点名称（如 `ChatOllama`、`search_knowledge_base`）和 **Duration**，判断慢在哪 |
| **怎么区分** | 口语里「这一 span 3 秒」≈「这个 Run 3 秒」。与 **print 一行日志** 不同：Run 带**结构化输入输出**和**与父 Run 的层级** |

### LangSmith

| 层 | 说明 |
|----|------|
| **是什么** | LangChain 官方提供的追踪与评测平台（[smith.langchain.com](https://smith.langchain.com/)），LangChain / LangGraph 集成时可通过环境变量自动上报 |
| **在本文干什么** | 注册账号 → 拿 API Key → 设 `LANGCHAIN_TRACING_V2` 等 → 跑 Agent → 在 **Projects** 里看 trace |
| **怎么区分** | **Langfuse / OpenTelemetry** 也能做追踪，配置方式不同；本文只走 **LangSmith 环境变量** 路径，不展开替代方案 |

### LangChain 自动追踪（环境变量）

| 层 | 说明 |
|----|------|
| **是什么** | LangChain 在 `LANGCHAIN_TRACING_V2=true` 且配置了 Key 时，会把 `invoke` / `stream` 等调用自动包装成 Run 上报 |
| **在本文干什么** | **不必**在 Agent 代码里写 `LangSmith` SDK；研究助手原样 `agent.invoke(...)` 即可 |
| **怎么区分** | **手动埋点** = 自己调 API 建 span；**自动追踪** = 改环境变量即可。本文是后者 |

| 变量 | 作用 | 忘记/用错会怎样 |
|------|------|-----------------|
| `LANGCHAIN_TRACING_V2=true` | 打开 v2 追踪 | 设为 `false` 或不设 → 本地照常跑，**后台无 trace** |
| `LANGCHAIN_API_KEY` | 认证 | 占位符或空 → 上报失败或脚本拒绝启动 |
| `LANGCHAIN_PROJECT` | 项目名（UI 里分组） | 不设 → 进 `default` 项目，仍可能有 trace |

### Agent 与 Tool（在 Trace 里长什么样）

| 层 | 说明 |
|----|------|
| **是什么** | **Agent** = 模型 + 工具 + 决策循环。**Tool** = 带 schema 的可调用函数（如 `search_knowledge_base(query: str)`） |
| **在本文干什么** | Trace 里通常能看到：**模型 Run**（生成 tool call）→ **Tool Run**（真正检索）→ **模型 Run**（根据 Observation 作答） |
| **怎么区分** | **模型慢**：某个 `ChatOllama` / `ChatModel` Run 耗时很长（如 30s）。**检索慢**：`search_knowledge_base` Run 绿且 2s。**参数错**：Tool Run **红**，详情里 Pydantic 报 `Input should be a valid string` |

### Ollama 与 tool calling

| 层 | 说明 |
|----|------|
| **是什么** | Ollama 本地跑开源模型；LangChain 通过 `ollama:模型名` 调用。小模型做 **function calling** 时，有时会把参数发成 `{text, type}` 对象而不是纯字符串 |
| **在本文干什么** | 工具定义要求 `query: str`，模型却传对象 → **工具未真正执行**，Trace 在 tool 节点报错；总耗时仍可能主要在**两轮模型**上 |
| **怎么区分** | 这是 **模型输出格式** 问题，不是 LangSmith 坏了；换更大模型或改 prompt 可能缓解。追踪的价值是**快速定位到 tool 节点**，而不是猜 |

---

## 要解决什么问题

| 场景 | 只有 print | 加上 LangSmith |
|------|------------|----------------|
| 总耗时 8s | 不知道 8s 花在哪 | 树上看模型 ~4s + ~4s，工具 0s（失败） |
| 工具有没有跑 | 可能只有报错一行 | Tool Run 红色 + 完整 validation 详情 |
| 线上复现 | 难对齐某次用户会话 | 按 Project / 时间 / input 找对应 Run |

---

## 环境准备（从零开始）

### 1. LangSmith 账号与 API Key

1. 打开 [https://smith.langchain.com](https://smith.langchain.com) 注册  
2. **Settings → API Keys** 创建 Key（形如 `lsv2_pt_...`）  
3. Key 只放本地 `.env`，**不要**提交到 Git  

### 2. Ollama 与模型

```bash
# 安装见 https://ollama.com
ollama pull qwen2:7b
ollama list   # 确认模型在列表里
```

### 3. Python 依赖（最小 Agent 示例）

新建空目录，创建 `pyproject.toml`：

```toml
[project]
name = "langsmith-tracing-demo"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "langchain>=0.3",
  "langchain-ollama>=0.2",
  "langchain-core>=0.3",
]
```

```bash
uv sync
# 或: pip install langchain langchain-ollama langchain-core
```

---

## 完整代码

### `.env`（复制为本地文件，勿提交）

```bash
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_你的真实Key
LANGCHAIN_PROJECT=day29-research-assistant

OLLAMA_MODEL=qwen2:7b
```

### `traced_agent.py`（最小可运行 Agent）

```python
"""LangSmith 自动追踪示例：环境变量打开后，invoke 即上报 trace。"""

from __future__ import annotations

import os
import sys

from langchain.agents import create_agent
from langchain.tools import tool

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")


@tool
def search_knowledge_base(query: str) -> str:
    """检索本地知识库。问内部协议、桶数时用本工具。"""
    # 教学用假数据；真实项目里接向量库
    return f"[mock KB] 关于「{query}」：协议 N7-2026，桶数 128。"


def main() -> None:
    question = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "内部协议版本和桶数分别是什么？请查知识库。"
    )

    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=[search_knowledge_base],
        system_prompt="你是研究助手。内部细节必须调用 search_knowledge_base，根据工具结果用中文简洁回答。",
    )

    print(f"Q: {question}\n")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    last = result["messages"][-1]
    print(f"Answer: {last.content}")


if __name__ == "__main__":
    main()
```

### `run_traced.sh`（加载 `.env` 再跑）

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "请先: cp .env.example .env 并填入 LANGCHAIN_API_KEY"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

if [[ -z "${LANGCHAIN_API_KEY:-}" || "${LANGCHAIN_API_KEY}" == "lsv2_pt_xxxxxxxx" ]]; then
  echo "请填入真实 LANGCHAIN_API_KEY，勿留占位符"
  exit 1
fi

echo "LangSmith project: ${LANGCHAIN_PROJECT:-default}"
uv run python traced_agent.py "${1:-内部协议版本和桶数分别是什么？请查知识库。}"
echo "打开 https://smith.langchain.com → Projects → ${LANGCHAIN_PROJECT:-default}"
```

```bash
chmod +x run_traced.sh
```

---

## 这段代码在干什么

1. **`@tool` + `query: str`**：LangChain 把函数 schema 发给模型；模型应返回 `{"name":"search_knowledge_base","args":{"query":"..."}}`  
2. **`create_agent` + `ollama:...`**：LangGraph 风格循环；每一轮模型、每次工具调用都会被 LangSmith 记成 Run  
3. **无 LangSmith import**：追踪由进程环境变量在 import LangChain 时生效  
4. **`run_traced.sh`**：保证跑之前 `LANGCHAIN_*` 已 export；并拒绝 example 占位 Key  

---

## 启动与验证

### 打开追踪

```bash
cp .env.example .env   # 若你从 example 复制
# 编辑 .env 填入真实 Key
./run_traced.sh
```

**期望终端**：打印问题和 Answer（或工具参数错误时的异常栈）；最后一行提示打开 LangSmith 项目 URL。

### 关闭追踪

任选其一：

- `.env` 里设 `LANGCHAIN_TRACING_V2=false`，或删除该行  
- 临时：`unset LANGCHAIN_TRACING_V2 LANGCHAIN_API_KEY` 后再跑  

Agent 行为不变，只是不再上报。

### 在 UI 确认生效

1. 打开 [https://smith.langchain.com](https://smith.langchain.com)  
2. 左侧 **Projects** → 选 `day29-research-assistant`（或你的 `LANGCHAIN_PROJECT`）  
3. 最新一条 **Run** → 进入 **Trace** 视图  
4. 应看到类似层级：**根 Run（Agent）** → **ChatOllama** → **search_knowledge_base** → **ChatOllama**  

| 检查项 | 说明 |
|--------|------|
| 有新 Run | 时间与本地执行一致 |
| 有 Duration | 各节点右侧有毫秒/秒 |
| 点 Tool 节点 | Inputs / Outputs 或 Error 面板有内容 |

### 怎么读 Trace 找瓶颈（三步）

| 你看到的 | 优先怀疑 |
|----------|----------|
| 某个 **模型 Run** 单独 30s | **LLM / Ollama 慢**（模型大小、机器、并发） |
| **search_knowledge_base** 绿且 2s | **RAG / 检索慢**（向量库、embedding、top_k） |
| **Tool Run 红**，`Input should be a valid string` | **参数格式错**（模型没按 schema 传 `str`），检索可能**根本没跑** |

```text
Trace 总 ~8s 的一例（工具参数失败时）：
  Agent/graph        ~8s
    ├─ model         ~4s   ← 第一轮：决定调工具
    ├─ tool          失败   ← 参数不是 string，RAG 未执行
    └─ model         ~4s   ← 第二轮：可能瞎编或道歉
```

---

## 踩过的坑

### 1. 占位符 Key 被当成「已配置」

**现象**：脚本或文档用 `lsv2_pt_*` 判断「是否像 LangSmith Key」，误伤真实 Key（真实 Key 也是 `lsv2_pt_` 开头）。  

**处理**：只拒绝**精确占位符** `lsv2_pt_xxxxxxxx`，不要用通配符匹配全部 `lsv2_pt_*`。

### 2. 追踪开了但 UI 没有 Run

**现象**：本地跑完，Projects 为空。  

**原因**：`LANGCHAIN_TRACING_V2` 未 export；或在设变量**之前**已 import langchain；或 Key 无效。  

**处理**：用 shell `source .env` 再启动 Python；同一 shell 里 `echo $LANGCHAIN_TRACING_V2` 应为 `true`；换 Key 重试。

### 3. Tool 报 validation error，总耗时仍在模型上

**现象**：Trace 里 tool 红叉，但 8s 里大部分在两个 model 节点。  

**原因**：Ollama 小模型 tool call 格式不稳定，把 `query` 发成对象。  

**处理**：Trace 已定位到 **tool 节点**；业务上换模型 / 调 prompt / 加 output parser。本文**不**把 LangSmith 和「修模型格式」混为一谈。

---

## 取舍与未做之事

| 做了 | 故意没做 |
|------|----------|
| LangSmith + 环境变量 + 现有 Agent | Langfuse / OpenTelemetry 实装 |
| Trace 树读延迟与错误类型 | Prometheus 指标、Grafana 大盘（常见下一主题） |
| 本地 Ollama Agent 示例 | 改 Day21 源码加手动 span |
| 占位符 Key 校验 | 生产级采样率、PII 脱敏策略 |

---

## 小结

- **链路追踪**比 `print` 多的是：**层级、每步耗时、结构化输入输出、错误挂载在具体 Run 上**。  
- Agent 的 Trace 里常见 **模型 Run** 与 **Tool Run** 交替出现。  
- **开关**：`LANGCHAIN_TRACING_V2` + `LANGCHAIN_API_KEY` +（可选）`LANGCHAIN_PROJECT`；到 LangSmith **Projects** 看到新 Run 即生效。  
- 排障口诀：**模型节点长 → LLM；工具节点长且绿 → 检索；工具节点红 → 参数/ schema**。  

下一步自然是用 **Prometheus** 等指标把「每次请求」推广成「整体健康度」——追踪负责单次，指标负责趋势。

---

*系列笔记 · Agent 工程跟练 · Week 5 Day 29*
