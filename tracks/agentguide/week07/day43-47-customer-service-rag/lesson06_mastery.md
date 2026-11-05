# Day43–47 Lesson 6 — 掌握检查

> 仅考已讲：需求分类、先库后 FAQ、step04 路径、小改动边界。

## 口述题（≥3）

1. 为什么客服要「先数据库精确查，再 FAQ 模糊检索」？  
2. 指着代码说：一条「查订单 ORD-1001 状态」请求在 `step04` 里怎么走？  
3. 各举一例：该走库 / 该走 FAQ / 该需人工。  

## 小改动

在 `data/seed.sql` 给 `SKU-99` 的 `stock` 改成别的数字（例如 `0`），`docker compose down -v && docker compose up -d` 后 curl：

```bash
curl -s http://127.0.0.1:8043/ask -H 'content-type: application/json' \
  -d '{"q":"SKU-99 库存多少？"}'
```

期望：`source=db`，库存是你改的数。说明为何生效（种子 → 表 → `lookup_product`）。
