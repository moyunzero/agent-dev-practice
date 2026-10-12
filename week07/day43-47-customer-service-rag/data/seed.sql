CREATE TABLE IF NOT EXISTS orders (
    order_id    TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL,
    status      TEXT NOT NULL,
    tracking_no TEXT
);

CREATE TABLE IF NOT EXISTS products (
    sku   TEXT PRIMARY KEY,
    name  TEXT NOT NULL,
    color TEXT,
    stock INT NOT NULL DEFAULT 0
);

INSERT INTO orders (order_id, user_id, status, tracking_no) VALUES
    ('ORD-1001', 'u_demo', 'shipped', 'SF123'),
    ('ORD-1002', 'u_demo', 'delivered', 'YT999'),
    ('ORD-1003', 'u_demo', 'processing', 'ZT777')
ON CONFLICT DO NOTHING;

INSERT INTO products (sku, name, color, stock) VALUES
    ('SKU-88', 'Demo Tee', 'red', 12),
    ('SKU-99', 'Demo Cap', 'black', 0)
ON CONFLICT DO NOTHING;
