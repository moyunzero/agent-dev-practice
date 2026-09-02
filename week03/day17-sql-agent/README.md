# Week 3 / Day 17 — SQL Agent

> **状态**：`available`
> 对外文章：[用自然语言查 SQLite：手写 SQL 工具 + LangChain Agent](../../notes/week03/day17-sql-agent.md)

## 前置

- Ollama（默认 `qwen2:7b`）  
- 无需 Docker / 外网数据库  

## 验收命令（全文）

```bash
cd week03/day17-sql-agent

uv sync
uv run python step01_init_and_peek.py
uv run python demo_sql_agent.py
# 或：
uv run python demo_sql_agent.py "外设类商品有哪些？最贵的是哪个？"
```

**期望**：peek 见 `products` / `sales`；Agent 轨迹含 `sql_db_*`；销量题 Answer 与 peek 中 `SUM(qty)` 最高商品一致。

## 脚本

| 脚本 | 用途 |
|------|------|
| `step01_init_and_peek.py` | 建 `data/shop.db` 并打印表 |
| `sql_tools.py` | list / schema / query（只读） |
| `demo_sql_agent.py` | `create_agent` SQL Agent |

## 收工后清理

```bash
rm -rf .venv __pycache__
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
# data/shop.db 可保留（练习数据，可由 step01 重建）
```
