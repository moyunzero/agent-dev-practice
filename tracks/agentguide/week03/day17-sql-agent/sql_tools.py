"""SQL 工具集：list_tables / schema / query（只读 SELECT）。"""

from __future__ import annotations

import re
import sqlite3

from langchain.tools import tool

from db_config import DB_PATH

# 极简护栏：拒绝明显写操作关键字（教学用，非生产级安全）
_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH)\b",
    re.IGNORECASE,
)


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"数据库不存在: {DB_PATH}。请先运行 step01_init_and_peek.py")
    return sqlite3.connect(DB_PATH)


@tool
def sql_db_list_tables() -> str:
    """列出数据库中所有用户表名（逗号分隔）。查询前应先调用本工具。"""
    con = _connect()
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return ", ".join(r[0] for r in rows) if rows else "(无表)"
    finally:
        con.close()


def _as_table_names(table_names: str | list) -> str:
    """小模型常把表名传成 list；统一收成逗号分隔字符串。"""
    if isinstance(table_names, list):
        return ",".join(str(t).strip() for t in table_names if str(t).strip())
    return str(table_names).strip()


@tool
def sql_db_schema(table_names: str | list[str]) -> str:
    """查看一张或多张表的建表语句，并各附最多 3 行样例数据。

    参数:
        table_names: 表名字符串，多个用逗号分隔，例如 "products" 或 "products,sales"。
                     也可以是字符串列表。
    """
    table_names = _as_table_names(table_names)
    if not table_names:
        return "请提供表名，例如 products 或 products,sales。"
    con = _connect()
    try:
        valid = {
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        parts: list[str] = []
        for name in [t.strip() for t in table_names.split(",") if t.strip()]:
            if name not in valid:
                parts.append(f"错误：表 {name!r} 不存在。已知表：{', '.join(sorted(valid))}")
                continue
            ddl = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone()
            parts.append(ddl[0] if ddl and ddl[0] else f"(无 DDL: {name})")
            quoted = '"' + name.replace('"', '""') + '"'
            cur = con.execute(f"SELECT * FROM {quoted} LIMIT 3")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()
            sample = "\t".join(cols) + "\n" + "\n".join("\t".join(str(c) for c in row) for row in rows)
            parts.append(f"/* 样例行 ({name}) */\n{sample}")
        return "\n\n".join(parts)
    finally:
        con.close()


@tool
def sql_db_query(query: str) -> str:
    """执行只读 SQL（SELECT），返回结果字符串。禁止写库语句。

    参数:
        query: 一条 SQLite SELECT 语句。出错时返回错误信息，可改写后重试。
    """
    q = query.strip().rstrip(";")
    if _WRITE_RE.search(q):
        return "拒绝执行：本工具只允许 SELECT 只读查询，禁止写库/改表。"
    # 允许 WITH ... SELECT；简单要求出现 SELECT
    if not re.search(r"\bSELECT\b", q, re.IGNORECASE):
        return "拒绝执行：请使用 SELECT（或 WITH ... SELECT）查询。"

    con = _connect()
    try:
        cur = con.execute(q)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        if not cols:
            return "(无结果列)"
        lines = ["\t".join(cols)]
        for row in rows[:50]:
            lines.append("\t".join(str(c) for c in row))
        if len(rows) > 50:
            lines.append(f"... 共 {len(rows)} 行，已截断前 50 行")
        return "\n".join(lines)
    except Exception as e:  # noqa: BLE001 — 返回给 Agent 的可读错误
        return f"SQL 错误: {e}"
    finally:
        con.close()


SQL_TOOLS = [sql_db_list_tables, sql_db_schema, sql_db_query]
