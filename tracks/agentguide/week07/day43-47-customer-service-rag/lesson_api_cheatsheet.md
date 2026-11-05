# Day43–47 API 速查（对照官方，禁瞎编）

## `psycopg.connect(conninfo)` — [Usage](https://www.psycopg.org/psycopg3/docs/basic/usage.html)

| | |
|--|--|
| **干什么** | 连上 PostgreSQL，返回 `Connection` |
| **入参** | `conninfo` 连接串，如 `postgresql://user:pass@host:port/dbname`；也可用关键字参数 |
| **出参** | `Connection`；作上下文管理器结束时关闭 |
| **何时用** | 每次查库前；本课用环境变量 `DATABASE_URL` |

## `Connection.execute(query, params)` / `Cursor.fetchone()` — [Params](https://www.psycopg.org/psycopg3/docs/basic/params.html)

| | |
|--|--|
| **干什么** | 执行 SQL；`fetchone` 取一行 |
| **入参** | SQL 里用 `%s` 占位；**参数必须走第二参元组**，禁止拼字符串（防注入） |
| **出参** | `execute` 返回 cursor；`fetchone()` → `tuple \| None` |
| **何时用** | 按订单号 / SKU **精确**查一行 |

```python
row = conn.execute(
    "SELECT order_id, status FROM orders WHERE order_id = %s",
    (oid,),
).fetchone()
```

## FastAPI `POST /ask`

| | |
|--|--|
| **干什么** | 收问句，返回 `answer` / `source` / `refs` / `need_human` |
| **本课** | 只实现库命中；无行或非 ORD/SKU → `need_human`（FAQ 在 Lesson 4） |
