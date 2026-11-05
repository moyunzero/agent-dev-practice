# 系统设计口述提纲（Day59–60）

## 通用四步

1. **澄清** — 范围 / 规模 / 延迟与可用性 / 失败是否可降级  
2. **架构** — 主路径组件与数据流  
3. **瓶颈/监控** — 热点、指标、告警  
4. **权衡** — 至少 1 个「选 A 不选 B」  

---

## 客服 RAG

1. **澄清**：订单/物流 vs FAQ；峰值 QPS、P99 目标；未命中是否转人工；订单是否必须实时查库（vs 分钟级缓存）  
2. **架构**：`POST /ask` → Postgres 精确查 → FAQ 回退 → 响应（可带 source）  
3. **瓶颈/监控**：库慢或 FAQ 扫库；Locust；Prom `/metrics` + Grafana；`request_id`  
4. **权衡**：先库后文档（准）；整栈 Compose 便于复现；缓存订单结果 vs 强一致实时查（可讨论）

---

## 投研 Multi-Agent

1. **澄清**：输入公司名；是否允许荐股（本仓：否）；工具失败能否降级；中间产出是否要审计  
2. **架构**：搜集 / 财报分析 / 撰写；`Process.sequential` + `context`；工具按职责挂载（≥5）  
3. **瓶颈/监控**：模型延迟与胡说；工具抖动 → tenacity + fixture；`intermediate/` 对账  
4. **权衡**：sequential 可审计 vs 并行更快但难交接；fixture 等价 API vs 强制付费 Key
