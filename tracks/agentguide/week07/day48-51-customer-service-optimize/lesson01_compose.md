# Day48–51 Lesson 1 — Compose 整栈（KP1）

> 挂钩上游：**部署: 使用 Docker Compose 部署**  
> 主攻：API 和 Postgres **一起**用 Compose 起，不只起库。

## 对照（本课唯一新点）

| | Day43–47 现状 | 本块整栈 |
|--|----------------|----------|
| Compose 里有什么 | 只有 `postgres` | `postgres` **+** `api` |
| API 怎么跑 | 宿主机 `uvicorn` | 容器里跑，Compose 起 |
| 验收 | 库健康即可 | 宿主机 `curl POST /ask` 通 |

口诀：**部署验收看「一键起完后能不能从外面调通 API」**，不是「库起来了」。

## 容器内连库

| | 宿主机跑 uvicorn | API 在 Compose 容器里 |
|--|------------------|----------------------|
| 主机 | `127.0.0.1` | 服务名 `postgres` |
| 端口 | 映射口 `5433` | 容器口 `5432` |
| 例 | `...@127.0.0.1:5433/...` | `...@postgres:5432/...` |

## 动手

1. 编辑 `docker-compose.yml`：把 `api.environment.DATABASE_URL` 从空串改成你预测的那一行  
2. 在本目录：`docker compose up -d --build`  
3. 验收：

```bash
curl -s http://127.0.0.1:8048/ask -H 'Content-Type: application/json' \
  -d '{"q":"订单 ORD-1001 到哪了？"}'
```

期望：`source` 为 `db`，答案里有状态/物流单号。
