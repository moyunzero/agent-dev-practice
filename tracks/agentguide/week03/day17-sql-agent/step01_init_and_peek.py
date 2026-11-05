"""第 1 课：建本地商店库 + 人眼 peek（不经过 LLM）。"""

from __future__ import annotations

import sqlite3

from db_config import DATA_DIR, DB_PATH


SCHEMA_SQL = """
DROP TABLE IF EXISTS sales;
DROP TABLE IF EXISTS products;

CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price_cny REAL NOT NULL
);

CREATE TABLE sales (
    id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    sold_on TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);
"""

SEED_PRODUCTS = [
    (1, "键盘", "外设", 299.0),
    (2, "鼠标", "外设", 129.0),
    (3, "显示器", "显示", 1599.0),
    (4, "笔记本支架", "外设", 89.0),
    (5, "耳机", "外设", 199.0),
]

SEED_SALES = [
    (1, 1, 3, "2026-08-01"),
    (2, 1, 2, "2026-08-10"),
    (3, 2, 5, "2026-08-05"),
    (4, 3, 1, "2026-08-12"),
    (5, 2, 2, "2026-08-20"),
    (6, 4, 4, "2026-08-22"),
    (7, 5, 100, "2026-08-25"),
]


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.executescript(SCHEMA_SQL)
        con.executemany(
            "INSERT INTO products (id, name, category, price_cny) VALUES (?, ?, ?, ?)",
            SEED_PRODUCTS,
        )
        con.executemany(
            "INSERT INTO sales (id, product_id, qty, sold_on) VALUES (?, ?, ?, ?)",
            SEED_SALES,
        )
        con.commit()
    finally:
        con.close()


def peek() -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        tables = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        print(f"数据库文件: {DB_PATH}")
        print(f"表: {', '.join(tables)}\n")

        print("=== products（商品）===")
        for row in con.execute("SELECT * FROM products"):
            print(dict(row))

        print("\n=== sales（销量明细）===")
        for row in con.execute("SELECT * FROM sales"):
            print(dict(row))

        print("\n=== 人写 SQL 示例：各商品总销量 ===")
        sql = """
        SELECT p.name, SUM(s.qty) AS total_qty
        FROM sales s
        JOIN products p ON p.id = s.product_id
        GROUP BY p.name
        ORDER BY total_qty DESC
        """
        print(sql.strip())
        for row in con.execute(sql):
            print(dict(row))
    finally:
        con.close()


def main() -> None:
    print("=== 第 1 课：先建库、看清表，再谈 Agent ===\n")
    init_db()
    print(f"已写入: {DB_PATH}\n")
    peek()
    print("\n要点：Agent 不会「魔法懂库」——它靠工具读表结构，再生成 SELECT。")


if __name__ == "__main__":
    main()
