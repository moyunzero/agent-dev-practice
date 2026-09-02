# Week 3 / Day 17 — SQL Agent

> **状态**：`available`  
> **长文教程**（可选）：[用自然语言查 SQLite](../../notes/week03/day17-sql-agent.md)

## 今日目标

自然语言查本地 SQLite：list tables / schema / 只读 query 工具 + LangChain SQL Agent。

## 前置

- Ollama（默认 `qwen2:7b`）
- 无需 Docker / 外网

## 文件说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `data/shop.db` | 运行 `step01` 后生成的 SQLite 商店库 |
| `db_config.py` | 数据库路径、连接 |
| `step01_init_and_peek.py` | **第 1 步**：建表、灌样例、打印 peek |
| `sql_tools.py` | **模块**：`sql_db_list_tables` / `schema` / `query`（只读） |
| `demo_sql_agent.py` | **第 2 步**：`create_agent` + 自然语言问句 |
| `pyproject.toml` / `uv.lock` | langchain、sqlite |

## 推荐顺序

| 步骤 | 命令 | 你会看到什么 |
|:----:|------|-------------|
| 0 | `uv sync` | 依赖 |
| 1 | `step01_init_and_peek.py` | `products` / `sales` 表与样例行 |
| 2 | `demo_sql_agent.py` | Agent 轨迹 + 答案 |
| 3 | 换问句再跑 | 验证 SQL 与 peek 一致 |

## 验收命令（汇总）

```bash
cd week03/day17-sql-agent
uv sync
uv run python step01_init_and_peek.py
uv run python demo_sql_agent.py "哪个商品总销量最高？卖了多少件？"
```

## 验收标准

- 轨迹含 `sql_db_list_tables` / `schema` / `query`
- 答案数字与 peek 中 `SUM(qty)` 一致

## 收工清理

```bash
rm -rf .venv __pycache__
# data/shop.db 可保留；删后 step01 可重建
```
