# 简历项目块（Day57–58 带练稿）

> 数字纪律：标「本仓实测」的可写死；标「占位 XX」的勿假装线上业务指标。

---

## 项目一：企业级智能客服 RAG（电商）

**一句话：** 为电商场景搭建「先查库、再 FAQ」的智能客服 API，并完成监控与 Compose 整栈部署。

**Bullets（草稿 · Lesson 2 起填）：**

- 实现电商客服 POST /ask：先 Postgres 精确查订单/SKU，未命中再 FAQ 回退；本机 Locust（库路径）QPS≈281，P99≈250ms（门槛 <500ms）。
- 以 Docker Compose 部署 API + Postgres + Prometheus + Grafana 整栈；Instrumentator 露出 `/metrics`，请求日志带 `request_id` 可对账；Grafana 看 QPS/P99 大盘。

**技术栈：** FastAPI · PostgreSQL · FAQ 文档回退 · Prometheus · Grafana · Docker Compose · Locust

---

## 项目二：自动化投研 Agent

**一句话：** 为投研分析师搭建「公司名 → 搜集→分析→成稿」的 CrewAI 多智能体流水线，中间产出可审计、工具层可降级。

**Bullets（草稿）：**

- 用 CrewAI 搭建搜集 / 财报分析 / 撰写三人小队，`Process.sequential` + `context` 接力；每步中间产出落盘 `intermediate/`，可审计分析是否完成。
- 集成 ≥5 工具（web_search / company_overview / sec_filings_search / parse_filing_metrics / write_report_file）；工具层 tenacity 重试 + fixture 降级，抖动下仍能交出可用文本。

**技术栈：** CrewAI · Ollama · 自定义 Tools（≥5）· tenacity · fixture 等价 Search/SEC
