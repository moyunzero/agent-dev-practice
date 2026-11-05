# AgentGuide 轨（阶段①）— 开发岗 Day 1–60

> **状态**：`available`  
> **轨登记**：[docs/TRACKS.md](../../docs/TRACKS.md) · **落地路线**：[docs/ROADMAP.md](../../docs/ROADMAP.md)  
> **上游**：[AgentGuide 开发岗路线](https://github.com/adongwanai/AgentGuide/blob/main/docs/05-roadmaps/learning-roadmap-development.md)

本目录是本仓阶段①的**全部可跑代码**（原仓库根下的 `week01/`…`week07/` 已迁入此处）。长文在 [`notes/weekXX/`](../../notes/)。

## 60 秒跑通

```bash
cd tracks/agentguide/week01/day01-fastapi-hello
cp .env.example .env
uv sync
uv run uvicorn main:app --reload --port 8000
```

## 周目录

| 周 | 主题 | 入口 |
|:--:|------|------|
| 1 | FastAPI + Naive RAG | [week01](./week01/) |
| 2 | Advanced RAG | [week02](./week02/) |
| 3 | Agent + Tools | [week03](./week03/) |
| 4 | 性能 | [week04](./week04/) |
| 5 | 可观测与部署 | [week05](./week05/) |
| 6 | Multi-Agent | [week06](./week06/) |
| 7–8 | 工业项目 + 面试 | [week07](./week07/) |

完整 Day 索引见根 [README.md](../../README.md)。通关后再看阶段②：[tracks/harness](../harness/)。
