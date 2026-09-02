# 用自然语言查 SQLite：手写 SQL 工具 + LangChain Agent

只会「把整张表贴进 Prompt」时，表一大就会撑爆上下文，而且模型仍可能胡写数字。  
**SQL Agent** 换了一种做法：让模型按需调用「列表 / 看结构 / 执行 SELECT」等工具，把**数据库返回的行**当作 Observation，再组织成人话答案。本文按上游 Day17 目标，用本地 SQLite 小商店库 + 三个 `@tool` + `create_agent`，从空目录跑通「哪个商品总销量最高」。

## 你将会得到什么

1. 说清 SQL Agent 与「整表塞 Prompt」的差别  
2. 建好 `products` / `sales` 两张表，并用人眼核对种子数据  
3. 实现只读三工具：`list_tables` / `schema` / `query`（拦写操作）  
4. 用 Ollama 跑自然语言问答，并避开：列名写错不重试、参数类型传 list、误用写语句  

---

## 零基础名词表

> 建议先读完再动手。

### 数据库 / 表 / 行 / 列

| 层 | 说明 |
|----|------|
| **是什么** | 数据库是按表格存数据的仓库；表是一类实体（商品、销量）；一行一条记录；列是字段（名称、价格） |
| **在本文干什么** | `products` 存商品；`sales` 存每次卖出多少件 |
| **怎么区分** | Excel 工作表 ≈ 表；但数据库用 **SQL** 精确查询，且可设关联 |

### SQL 与 SELECT

| 层 | 说明 |
|----|------|
| **是什么** | Structured Query Language，跟关系数据库说话的语言。`SELECT` = 只读查询 |
| **在本文干什么** | Agent 生成 `SELECT ... JOIN ... SUM(qty) ...`，由工具执行 |
| **怎么区分** | `INSERT/UPDATE/DELETE` 会改数据；教学 Agent **禁止**这些（工具层拦截） |

### SQLite

| 层 | 说明 |
|----|------|
| **是什么** | 轻量数据库：整个库通常是**一个文件**；Python 标准库 `sqlite3` 即可，免装服务器 |
| **在本文干什么** | `data/shop.db` 作为练习库 |
| **怎么区分** | 与 Postgres/MySQL 比：零运维、适合单机 demo；不是生产高并发首选 |

### 外键与 JOIN（关联）

| 层 | 说明 |
|----|------|
| **是什么** | `sales.product_id` 指向 `products.id`，把「卖了几件」和「商品叫什么」连起来 |
| **在本文干什么** | 问「哪个商品销量最高」时，常要 `JOIN products` 才能说出名称 |
| **怎么区分** | 只查 `sales` 可能只得到 `product_id=5`；要名称必须关联或再查 `products` |

### SQL Agent

| 层 | 说明 |
|----|------|
| **是什么** | 会调用「查库工具」的 Agent：模型写 SQL，工具执行，Observation 回传结果 |
| **在本文干什么** | 自然语言 → `create_agent` → 三工具循环 → 中文答案 |
| **怎么区分** | 不是魔法懂库：没看 schema 就容易写错列名（如把 `qty` 写成 `quantity`） |

```text
问句
  → sql_db_list_tables   （有哪些表）
  → sql_db_schema        （列叫什么）
  → sql_db_query         （执行 SELECT）
  → Observation（真实行）
  → Answer（人话；数字必须来自 Observation）
```

### 只读护栏 `_WRITE_RE`

| 层 | 说明 |
|----|------|
| **是什么** | 用正则拦截 SQL 里的 INSERT/UPDATE/DELETE/DROP 等关键字 |
| **在本文干什么** | `sql_db_query` 发现写操作就拒绝，返回错误字符串给 Agent |
| **怎么区分** | **教学级**防护，不是生产级安全（真生产还要账号权限、SQL 解析器等） |

### `create_agent`（与 Day15/16 相同）

LangChain ≥1.3：`from langchain.agents import create_agent`，可用 `model="ollama:..."` 与 `system_prompt=`。勿与旧文 `create_react_agent` 的参数混用。

---

## 环境准备

- Python 3.12+、[uv](https://docs.astral.sh/uv/)  
- [Ollama](https://ollama.com/) + 模型（如 `qwen2:7b`）  
- 无需 Docker、无需外网数据库  

```bash
ollama pull qwen2:7b
```

---

## 从空目录复现

```bash
mkdir day17-sql-agent && cd day17-sql-agent
```

### `pyproject.toml`

```toml
[project]
name = "day17-sql-agent"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "langchain>=1.3.16",
    "langchain-ollama>=1.1.0",
    "langgraph>=0.4.0",
]
```

```bash
uv sync
```

### 步骤 1：建库并 peek（无 LLM）

`db_config.py`：

```python
from pathlib import Path
DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "shop.db"
```

`init_db.py`（节选逻辑：建 `products`/`sales`，写入种子；完整可对照练习仓脚本）：

- 商品含键盘、鼠标、耳机等  
- 销量明细用 `product_id` + `qty`  
- 打印各商品 `SUM(qty)`，确认最高销量商品  

```bash
uv run python init_db.py   # 或 step01_init_and_peek.py
```

**先用人眼看清库**，再开 Agent——否则你无法判断模型是否答对。

### 步骤 2：三个 SQL 工具

核心接口（与现版 [LangChain SQL Agent 文档](https://docs.langchain.com/oss/python/langchain/sql-agent) 同一思路：自建工具 + `create_agent`）：

1. **`sql_db_list_tables`**：返回表名  
2. **`sql_db_schema(table_names)`**：DDL + 最多 3 行样例；`table_names` 建议字符串 `"sales"`，并兼容小模型误传的 list  
3. **`sql_db_query(query)`**：只执行含 `SELECT` 的语句；命中写操作关键字则拒绝  

`sql_db_query` 护栏示意：

```python
import re
_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE)\b",
    re.I,
)

def sql_db_query(query: str) -> str:
    q = query.strip().rstrip(";")
    if _WRITE_RE.search(q):
        return "拒绝执行：只允许 SELECT。"
    if not re.search(r"\bSELECT\b", q, re.I):
        return "拒绝执行：请使用 SELECT。"
    # sqlite3 执行，返回表格字符串；出错返回 "SQL 错误: ..."
```

### 步骤 3：挂进 Agent

```python
from langchain.agents import create_agent
from sql_tools import SQL_TOOLS  # 上面三个工具

SYSTEM = """你是 SQLite 助手。必须用工具查库，禁止编造数字。
先 list_tables，再 schema，再 query。
列名必须与 schema 一致（销量列是 qty 不是 quantity）。
若 query 报 SQL 错误：改写后再次调用 query，不要只口头纠正。
需要商品名时 JOIN products。禁止写库。"""

agent = create_agent(
    model="ollama:qwen2:7b",
    tools=SQL_TOOLS,
    system_prompt=SYSTEM,
)
result = agent.invoke(
    {"messages": [{"role": "user", "content": "哪个商品总销量最高？卖了多少件？"}]}
)
```

期望轨迹包含：`sql_db_list_tables` → `sql_db_schema` → `sql_db_query`，Observation 中出现最高销量数字；Answer 引用该数字。

---

## 新手坑

### 1. 列名幻觉：`quantity` vs `qty`

| | |
|--|--|
| **现象** | `SQL 错误: no such column: quantity` |
| **原因** | 模型凭英语常识猜列名，没严格用 schema 里的 `qty` |
| **处理** | schema 先看样例行；system_prompt 要求「列名完全一致」；**出错必须再调 query** |

### 2. `table_names` 传成 JSON 数组

| | |
|--|--|
| **现象** | `Input should be a valid string` |
| **原因** | 小模型传 `["sales"]` 而不是 `"sales"` |
| **处理** | 工具侧兼容 `str | list`；prompt 写明用字符串 |

### 3. 报错后只「建议改 SQL」却不重试

| | |
|--|--|
| **现象** | Answer 说「应该用 qty」但没有新的 Observation |
| **原因** | prompt 软约束；小模型偷懒 |
| **处理** | 明确写「必须再次调用 sql_db_query」；必要时换更强模型 |

### 4. 只得到 `product_id` 没有商品名

| | |
|--|--|
| **处理** | `JOIN products`，或再查 `products` 表 |

### 5. 未先建库

| | |
|--|--|
| **现象** | 文件不存在 |
| **处理** | 先跑建库 / peek 脚本 |

---

## 本文边界

**做了什么**：SQLite 只读 SQL Agent；三工具；自然语言聚合查询；常见翻车与护栏。  

**故意没展开**：写库、多用户权限、Postgres、生产 SQL 注入加固、MCP。

---

## 延伸阅读

- [LangChain SQL Agent](https://docs.langchain.com/oss/python/langchain/sql-agent)  
- [Open-Meteo 式「工具封装」思路](https://docs.langchain.com/oss/python/langchain/tools)（与 Day16 同一 `@tool` 机制）  

---

## 收束

1. SQL Agent = **按需查库工具** + ReAct，不是整表塞 Prompt。  
2. 标准节奏：list → schema → query；数字以 Observation 为准。  
3. 列名以 schema 为准；SQL 错了要**重试工具**，护栏挡住写操作。
