# 学习路线

> 上游原文：[AgentGuide · learning-roadmap-development.md](https://github.com/adongwanai/AgentGuide/blob/main/docs/05-roadmaps/learning-roadmap-development.md)  
> 本文是本仓库的**跟练落地版**：保留原文强制目标，按本仓技术栈裁剪/扩展。

---

## 1. 目标与产出

| 项 | 约定 |
|----|------|
| 上游权威 | [AgentGuide 开发岗路线](https://github.com/adongwanai/AgentGuide/blob/main/docs/05-roadmaps/learning-roadmap-development.md) 的每日「学习内容 / 手撕 / 解锁技能 / 目标」 |
| 结束标准 | 能讲清上游目标、能跟脚本做小改动、验收命令跑通 |
| 岗位 | AI Agent 开发工程师（工程落地） |
| 节奏 | 全职 · 约 8 周 |
| 模型 | Ollama（本地）+ OpenRouter（免费云端） |
| 每日闭环 | 对准上游目标 → 跟练 → 写对外文章 → 同步公开文档 |
| 最终产出 | 与原文一致方向：可部署的 RAG/Agent 能力 + 第 7–8 周简历级项目 |

**本仓文档只负责落地方式（技术栈、文章、门禁）；不得用「本仓扩展」替换或缩水上游强制学习目标。**

---

## 2. 总览（8 周）

| 周 | 主题 | 本周结束时应能演示 |
|----|------|-------------------|
| 1 | FastAPI + LangChain + Naive RAG | 文档问答 API + Docker 跑起来 |
| 2 | Advanced RAG + 向量库 + 评估 | 混合检索/Rerank + 评估报告 + Milvus（或等价） |
| 3 | Agent + Tool Calling | 带工具的研究助手（含重试/降级） |
| 4 | 性能优化 | Redis 缓存、异步、批处理、压测指标 |
| 5 | 可观测与部署 | Trace + Prometheus/Grafana 思路 + Compose 一键起 |
| 6 | Multi-Agent | AutoGen / CrewAI（或现役等价）各一协作 Demo |
| 7–8 | 工业项目 + 面试 | 智能客服 RAG + 投研 Multi-Agent；简历量化表述 |

细节以原文周计划为准；下面把 **第 1 周按天拆到可执行**，并写明本仓扩展边界。

---

## 3. Day 1–28 详细计划

### Day 1 — FastAPI 基础 + 双后端连通 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 路由；path / query / body；可运行 Hello API |
| 本仓扩展 | Ollama + OpenRouter；Pydantic 校验 `temperature` |
| 文章 | [notes/week01/day01-fastapi.md](../notes/week01/day01-fastapi.md) |
| 代码 | `week01/day01-fastapi-hello/` |

### Day 2 — LangChain 核心 + LCEL **available**

> 文章：[notes/week01/day02-langchain-lcel.md](../notes/week01/day02-langchain-lcel.md)

> 上游原文目标（**底线，不可缩水**）：  
> **理解 LangChain 六大核心模块，熟练使用 LCEL**；手撕第一条 LLM Chain。  
> 本仓可在此之上**增加**目标，但不得用扩展替代六大模块中的任一块。

#### 上游强制：六大核心模块（须全部「理解」）

采用经典六分法（与多数中文入门材料一致）：

| # | 模块 | Day2「学会」最低标准 |
|---|------|----------------------|
| 1 | **Models** | 能说明 Chat Model 是什么；会用 `ChatOpenAI`（含 `base_url` 接 Ollama/OpenRouter）发起一次调用 |
| 2 | **Prompts** | 能说明 Prompt Template 作用；会写 `ChatPromptTemplate`（system/human + 变量） |
| 3 | **Chains** | 能说明 Chain = 组件流水线；**熟练 LCEL**：会写并讲解 `prompt \| model \| parser` |
| 4 | **Memory** | 能说明为何需要 Memory、和「无状态 LLM」的关系；能口述常见用法（当日可用最小示例或清晰口述，深度实战在 Week3） |
| 5 | **Indexes** | 能说明 Index/检索相关组件解决什么问题（文档→切分→向量→检索）；与后面 RAG 天的衔接说得清（深度实战在 Day3–6） |
| 6 | **Agents** | 能说明 Agent 与普通 Chain 的区别（会不会自己选工具）；知道 Tool Calling 方向（深度实战在 Week3） |

另：原文学习内容中的 **Output Parsers** 归入 Model I/O / Chain 链路，Day2 必须会用 `StrOutputParser`（或等价），并说清「为什么要 parser」。

#### 上游强制：手撕

- [x] 用 LCEL 编写第一条 LLM Chain，并能独立改 Prompt 观察到行为变化

#### 本仓可增加的目标（加法，可选）

- FastAPI `POST /chain` 暴露同一条 LCEL  
- 双后端切换（ollama / openrouter）  
- （其它你指定的加项）

#### 结束标准（学会了才 done）

- 六大模块均能用自己的话讲清「是什么 / 解决什么问题 / 和其它模块关系」  
- LCEL 链：能画数据流，能独立改，能过掌握题  
- 手撕 chain 可演示  
- 对外文章确认 + 同步公开文档  

#### 练习 / 文章

| | |
|--|--|
| 练习目录 | `week01/day02-langchain-lcel/` |
| 文章产出 | `notes/week01/day02-langchain-lcel.md`（零基础自洽；六大模块都要写进正文，不能只写 LCEL） |

**Day 2 建议课时结构（确认后执行）**

1. 复述 Day1 小结  
2. 总览六大模块地图（先建立全图，再深入 LCEL）  
3. Models + Prompts + Output Parser 实操  
4. Chains / LCEL 手撕与熟练练习  
5. Memory / Indexes / Agents：概念打透 + 最小示意（为后续周埋点，不偷换「理解」为「跳过」）  
6. （加法）FastAPI `/chain` 等扩展  
7. 掌握检查（含六大模块口述）→ 文章 → 同步公开文档  

### Day 3 — RAG Part 1：加载与分割 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | Document Loader、Text Splitter；PDF/MD 加载与分块策略 |
| 本仓倾向 | 先 MD/纯文本，再 PDF；RecursiveCharacter + MarkdownHeader 对比 |
| 验收 | 给定文档 → chunk 列表；能说清策略选型与 chunk 参数 |
| 文章 | [notes/week01/day03-rag-load-split.md](../notes/week01/day03-rag-load-split.md) |

### Day 4 — RAG Part 2：向量化与存储 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | Embedding 直觉；本地向量库 FAISS 或 Chroma |
| 本仓倾向 | Chroma 持久化 + sentence-transformers 本地 Embedding |
| 验收 | chunk 入库 → 问句 Top-K 检索可见 |
| 文章 | [notes/week01/day04-rag-embed-store.md](../notes/week01/day04-rag-embed-store.md) |

### Day 5–6 — 手撕 Naive RAG ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | FastAPI + LangChain 端到端文档问答 API |
| 本仓串联 | Day1 服务 + Day2 LCEL + Day3/4 检索 → `POST /ask` |
| 验收 | 问句 → 检索 → 生成；返回 `answer` + `sources` |
| 文章 | [notes/week01/day05-06-naive-rag.md](../notes/week01/day05-06-naive-rag.md) |

### Day 7 — Docker 打包 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 本周 RAG 用 Docker 打包并成功运行 |
| 本仓串联 | `day05-06-naive-rag` → Dockerfile + `docker build` / `docker run` |
| 验收 | 容器内 `/health` 与 `POST /ask` 可复现；宿主机 Ollama + HF 缓存挂载 |
| 文章 | [notes/week01/day07-docker.md](../notes/week01/day07-docker.md) |

### Day 8 — Query Transformation ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 实现 HyDE、Multi-Query 等查询改写策略 |
| 本仓串联 | Week1 Chroma 检索前加改写；CLI 对比 `none` / `multi_query` / `hyde` |
| 验收 | Multi-Query + HyDE 可演示；假资料不作最终答案；掌握检查通过 |
| 文章 | [notes/week02/day08-query-transform.md](../notes/week02/day08-query-transform.md) |

### Day 9 — 混合检索与 Rerank ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 实现 BM25 + Embedding 混合检索，并集成 Reranker |
| 本仓串联 | BM25 + Chroma 向量 + RRF 融合；CrossEncoder 精排；四档对比 CLI |
| 验收 | vector / BM25 / hybrid / hybrid+rerank 可演示；掌握检查通过 |
| 文章 | [notes/week02/day09-hybrid-rerank.md](../notes/week02/day09-hybrid-rerank.md) |

### Day 10–11 — RAG 评估体系 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 学习 RAG 核心评估指标，并用 RAGAs 评估优化前后的系统性能 |
| 本仓串联 | Faithfulness / Answer Relevancy；RAGAs + Ollama Judge；Naive vs Hybrid+Rerank；`eval_pipeline` |
| 验收 | 指标直觉 + baseline + 对比 + 流水线 CLI；掌握检查通过 |
| 文章 | [notes/week02/day10-11-ragas-eval.md](../notes/week02/day10-11-ragas-eval.md) |

### Day 12 — Milvus 向量库 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 使用 Docker 部署 Milvus，并掌握其 Python SDK |
| 本仓串联 | Compose Standalone；MilvusClient 建表 / CRUD / Top-K；RAG 半链路与 Chroma 对照；带 `text` 字段 |
| 验收 | `docker compose up` + SDK CRUD + `demo_rag_search`；掌握检查通过 |
| 文章 | [notes/week02/day12-milvus.md](../notes/week02/day12-milvus.md) |

### Day 13 — 复杂 PDF / Unstructured ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 使用 Unstructured/MinerU 解析包含表格、图片的复杂 PDF |
| 本仓串联 | PyPDF 对照；`partition_pdf` fast/hi_res；`Table` + `text_as_html`；Element → Document → Splitter |
| 验收 | 三课 demo + 掌握检查；MinerU 边界知悉 |
| 文章 | [notes/week02/day13-unstructured-pdf.md](../notes/week02/day13-unstructured-pdf.md) |

### Day 14 — 周度升级 Hybrid + Rerank + Milvus ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 将第一周的 RAG 系统升级，集成混合检索、Reranker 和 Milvus |
| 本仓串联 | Milvus 入库；BM25∥向量 RRF；CrossEncoder Rerank；Naive vs Upgraded；可选 Ollama；**FastAPI `/ask`** |
| 验收 | 三档对照 + 掌握检查；文章含 Compose / 版本说明 + API；补洞 curl 通 |
| 文章 | [notes/week02/day14-rag-upgrade.md](../notes/week02/day14-rag-upgrade.md) |

### Day 15 — Agent 核心 / ReAct ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 理解 ReAct 框架，并运行一个 LangChain 官方的 Agent 示例 |
| 本仓串联 | Thought/Action/Observation；`create_agent` + `@tool` + Ollama；schema / docstring；小改动 `add` |
| 验收 | 三课 demo + 掌握检查；文章含版本 import、软约束 prompt、Answer 末条规则 |
| 文章 | [notes/week03/day15-react-agent.md](../notes/week03/day15-react-agent.md) |

### Day 16 — 自定义天气工具 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 编写一个查询天气的自定义工具，并集成到 Agent 中 |
| 本仓串联 | Open-Meteo（城市→经纬度→预报）；`@tool`；`create_agent`；`WEATHER_FAKE` 仅兜底 |
| 验收 | 真实 API invoke + Agent 轨迹；掌握检查（两步顺序 / 先测工具） |
| 文章 | [notes/week03/day16-custom-weather-tool.md](../notes/week03/day16-custom-weather-tool.md) |

### Day 17 — SQL Agent ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 构建一个能根据自然语言查询数据库的 SQL Agent |
| 本仓串联 | SQLite shop.db；list/schema/query 只读；`create_agent`；列名重试与参数兼容 |
| 验收 | peek + Agent 轨迹；掌握检查；文章含护栏与常见坑 |
| 文章 | [notes/week03/day17-sql-agent.md](../notes/week03/day17-sql-agent.md) |

### Day 18 — Function Calling ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 使用 OpenAI API 实现一个能根据用户问题调用函数的 Agent |
| 本仓串联 | openai SDK；tools/tool_calls/role=tool 两轮；Ollama 兼容或真 OpenAI；订单查询 |
| 验收 | 协议课 + demo；掌握检查；改 ORDERS 后答案跟随 |
| 文章 | [notes/week03/day18-function-calling.md](../notes/week03/day18-function-calling.md) |

### Day 19 — Agent Memory ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 为 Agent 添加对话历史记忆 (ConversationBufferMemory) |
| 本仓串联 | 无记忆对照；InMemorySaver + thread_id；与 BufferMemory 概念对齐；Mem0 边界 |
| 验收 | 同 thread 记得 / 换 thread 忘掉；掌握检查 |
| 文章 | [notes/week03/day19-agent-memory.md](../notes/week03/day19-agent-memory.md) |

### Day 20 — Agent 错误处理 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 为工具调用添加重试机制 (tenacity) 和降级策略 |
| 本仓串联 | 假抖动查价；无重试对照；@retry + 缓存降级；挂进 create_agent |
| 验收 | stop=3 得实时价；stop=2 走降级；掌握检查 |
| 文章 | [notes/week03/day20-agent-error-handling.md](../notes/week03/day20-agent-error-handling.md) |

### Day 21 — 研究助手 Agent ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 构建集成 RAG 和 Web 搜索工具的研究助手 Agent |
| 本仓串联 | Nebula 本地笔记 + Chroma；DuckDuckGo web_search；create_agent 双工具 |
| 验收 | 内部题走知识库；改超时重建后答案跟随；掌握检查 |
| 文章 | [notes/week03/day21-research-assistant.md](../notes/week03/day21-research-assistant.md) |

### Day 22 — 性能瓶颈分析 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 使用 cProfile、py-spy 等分析现有 Agent 系统性能瓶颈 |
| 本仓串联 | 小流水线热身；`create_agent`+Ollama 实战；py-spy top（macOS 可 sudo） |
| 验收 | 真实 Agent 表上为等模型；掌握检查；对外文章 |
| 文章 | [notes/week04/day22-perf-profile.md](../notes/week04/day22-perf-profile.md) |

### Day 23 — 缓存优化 (Redis) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 为 Agent 系统添加 Redis 缓存，缓存 LLM 响应 |
| 本仓串联 | Compose Redis(6389)；`create_agent`+最终回答缓存；同问句 miss/hit 对比 |
| 验收 | hit 跳过模型；掌握检查（含检索缓存 vs 响应缓存）；对外文章 |
| 文章 | [notes/week04/day23-redis-cache.md](../notes/week04/day23-redis-cache.md) |

### Day 24–25 — 异步处理 (Async) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 将系统中 I/O 密集型操作 (如 API 调用) 改造为异步 |
| 本仓串联 | 优化手段地图；`gather`；FastAPI `async def`+`await`；反例 `time.sleep` 堵 loop |
| 验收 | 并发压测 ask≈0.4s vs block≈1.2s；掌握检查；对外文章 |
| 文章 | [notes/week04/day24-25-async.md](../notes/week04/day24-25-async.md) |

### Day 26 — 批处理优化 (Batching) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 实现 Embedding 和 Reranker 的批处理，提升吞吐量 |
| 本仓串联 | 玩具直觉；`embed_documents` vs `embed_query`；CrossEncoder 一批 `predict`；分批防 OOM |
| 验收 | 吞吐对比 + 掌握检查（含批 vs 异步）；对外文章 |
| 文章 | [notes/week04/day26-batching.md](../notes/week04/day26-batching.md) |

### Day 27 — 高性能推理 (vLLM) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 使用 vLLM 部署开源模型并测试吞吐量 |
| 本仓串联 | **路径 A-Metal**：vLLM-Metal + mlx-community 小模型；`vllm serve` + curl；串行 vs 并发吞吐脚本 |
| 验收 | chat completion 通；wall / req/s / completion_tok/s 能解释；掌握检查；对外文章 |
| 文章 | [notes/week04/day27-vllm.md](../notes/week04/day27-vllm.md) |

### Day 28 — 周度总结与性能压测 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 使用 locust 或 jmeter 对优化前后压测，记录 QPS、P99 |
| 本仓串联 | **Locust + JMeter 双工具**；Day24–25 `/async-ask` vs `/async-block`；Week4 地图收官 |
| 验收 | 两工具读出吞吐与 P99；前后对照能解释；掌握检查；对外文章 |
| 文章 | [notes/week04/day28-load-test.md](../notes/week04/day28-load-test.md) |

---

## 4. 第 5 周 ✅

### Day 29 — 链路追踪 (LangSmith) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 将 LangSmith 集成到现有 Agent 应用中，分析调用链路 |
| 本仓串联 | **路径 A-LangSmith**：环境变量接到 Day21 研究助手；Trace 树读模型/工具延迟与错误 |
| 验收 | Projects 出现完整 Run；能指着树讲清慢在哪；掌握检查；对外文章 |
| 文章 | [notes/week05/day29-tracing.md](../notes/week05/day29-tracing.md) |
| 代码 | [week05/day29-tracing](../week05/day29-tracing/) |

### Day 30 — 指标监控 (Prometheus) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 暴露 API 的 QPS, 延迟, 错误率等核心指标 |
| 本仓串联 | FastAPI + Instrumentator `/metrics`；自定义 `cache_lookups_total` hit/miss |
| 验收 | curl 见 requests / duration / cache Counter；掌握检查；对外文章 |
| 文章 | [notes/week05/day30-prometheus.md](../notes/week05/day30-prometheus.md) |
| 代码 | [week05/day30-prometheus](../week05/day30-prometheus/) |

### Day 31 — 可视化 (Grafana) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 安装 Grafana，并创建一个简单的监控大盘来展示 Prometheus 指标 |
| 本仓串联 | Compose Grafana+Prometheus；刮取 Day30；预置 4 Panel 大盘（含实拍） |
| 验收 | targets UP；Explore 有曲线；大盘可读；掌握检查；对外文章 |
| 文章 | [notes/week05/day31-grafana.md](../notes/week05/day31-grafana.md) |
| 代码 | [week05/day31-grafana](../week05/day31-grafana/) |

### Day 32 — 容器化 (Docker) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 为 FastAPI 应用编写 Dockerfile 并成功构建镜像 |
| 本仓串联 | Dockerfile + `day32-fastapi` 镜像；`-p 8032:8000`；含 `/metrics` |
| 验收 | build 成功；curl health/ask/metrics；掌握检查；对外文章 |
| 文章 | [notes/week05/day32-docker.md](../notes/week05/day32-docker.md) |
| 代码 | [week05/day32-docker](../week05/day32-docker/) |

### Day 33 — 服务编排 (Docker Compose) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 编写 `docker-compose.yml` 文件，一键启动整个应用栈 |
| 本仓串联 | FastAPI + Redis；服务名 DNS；health + miss→hit 验收（Milvus 可选） |
| 验收 | `compose up`；`/health` redis:true；掌握检查；对外文章 |
| 文章 | [notes/week05/day33-compose.md](../notes/week05/day33-compose.md) |
| 代码 | [week05/day33-compose](../week05/day33-compose/) |

### Day 34 — 日志系统 (JSON) ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 配置应用将日志输出为 JSON 格式，为接入 ELK 做准备 |
| 本仓串联 | FastAPI + structlog `JSONRenderer`；请求中间件；端口 `8034`（不强制本机 ELK） |
| 验收 | stdout 一行 JSON；含 `event`/`path`/`status`/`duration_ms`；掌握检查；对外文章 |
| 文章 | [notes/week05/day34-logging.md](../notes/week05/day34-logging.md) |
| 代码 | [week05/day34-logging](../week05/day34-logging/) |

### Day 35 — 周度总结与生产环境模拟 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 模拟一次线上故障，并使用本周学习的工具链进行问题定位 |
| 本仓串联 | `FAULT=slow|error` 注入；JSON 字段交叉定位；加码 A：ES+Kibana（19200/15601） |
| 验收 | slow/error 可复现；Kibana `status:500`/`fault:slow`；掌握检查；对外文章 |
| 文章 | [notes/week05/day35-incident.md](../notes/week05/day35-incident.md) |
| 代码 | [week05/day35-incident](../week05/day35-incident/) |

### Day 36–37 — AutoGen 核心概念 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 学习 `ConversableAgent`、`GroupChat` 等核心概念，并运行官方示例 |
| 本仓串联 | 现役 AgentChat 0.7.x：`AssistantAgent` + `RoundRobinGroupChat`；`autogen-agentchat` + `autogen-ext[ollama]`；Ollama |
| 验收 | 单助手 `run`；双助手轮转见 `writer`/`critic`；掌握检查；对外文章 |
| 文章 | [notes/week06/day36-37-autogen-core.md](../notes/week06/day36-37-autogen-core.md) |
| 代码 | [week06/day36-37-autogen-core](../week06/day36-37-autogen-core/) |

### Day 38 — AutoGen 实战 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 实现一个"研究员-程序员-测试员"的 Multi-Agent 系统 |
| 本仓串联 | 三 `AssistantAgent` + `RoundRobinGroupChat`；Ollama；短任务演示协作 |
| 验收 | 终端见 researcher/coder/tester 交替；掌握检查；对外文章 |
| 文章 | [notes/week06/day38-autogen-team.md](../notes/week06/day38-autogen-team.md) |
| 代码 | [week06/day38-autogen-team](../week06/day38-autogen-team/) |

### Day 39–40 — CrewAI 核心概念 ✅

| | |
|--|--|
| 状态 | **available** |
| 强制 | 学习 Agent, Task, Crew, Process 的概念，并运行官方示例 |
| 本仓串联 | `crewai[litellm]==1.15.20`；`LLM(ollama/...)` + sequential 双 Agent Crew |
| 验收 | `kickoff` 先研究后写；掌握检查；对外文章 |
| 文章 | [notes/week06/day39-40-crewai-core.md](../notes/week06/day39-40-crewai-core.md) |
| 代码 | [week06/day39-40-crewai-core](../week06/day39-40-crewai-core/) |

---

## 5. 第 6–8 周

Week 1–5 已发布（Day1–35 available）；Week 6 进行中（Day36–40 available）。

| 周 | 状态 | 强制主线 | 本仓注意 |
|----|------|----------|----------|
| 5 | `available` | 可观测 + Docker/Compose + JSON 日志 + 故障演练（Day29–35 ✅） | 见 [week05/README.md](../week05/README.md) |
| 6 | `in_progress` | AutoGen + CrewAI（或现役维护中的等价框架） | Day36–40：AgentChat + CrewAI 核心；见 [week06/README.md](../week06/README.md) |
| 7–8 | `planned` | 智能客服 RAG + 投研 Multi-Agent；简历与系统设计 | 部署以 Compose 为底线 |

---

## 6. 如何使用

1. 从根 [README.md](../README.md) 选 Day，进入对应 `weekXX/dayYY-*/` 目录  
2. 阅读目录内 README 与 [notes/](../notes/) 文章  
3. 按验收命令跑通；需要 Docker / Ollama 的 day 会写在 README 前置里  
4. 完整 8 周索引见上文 §2 总览

