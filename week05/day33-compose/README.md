# Week 5 / Day 33 — Docker Compose 应用栈

> **状态**：`available`  
> **长文教程**（可选）：[用 Docker Compose 一键启动 FastAPI + Redis](../../notes/week05/day33-compose.md)

## 今日目标

编写 `docker-compose.yml`，一键启动 FastAPI + Redis 整栈，并验证服务间连通。

## 前置

- Docker Desktop  
- 端口：**8033**（API）、**6389**（Redis 宿主机可选）

## 文件说明

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | api + redis 编排 |
| `Dockerfile` / `app/` | API 镜像与 Redis 客户端逻辑 |
| `lesson01_compose_map.md` | 概念地图 |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 1 | 读 lesson01 | service / DNS / depends_on |
| 2 | `docker compose up -d --build` | 一键起栈 |
| 3 | curl `/health` 与两次 `/ask` | 验连通与缓存 |
| 4 | `docker compose down` | 收工 |

## 验收命令（汇总）

```bash
cd week05/day33-compose
docker compose up -d --build
docker compose ps

curl -s http://127.0.0.1:8033/health
curl -s 'http://127.0.0.1:8033/ask?q=hello'
curl -s 'http://127.0.0.1:8033/ask?q=hello'

docker compose down
```

**期望**：redis healthy、api Up；health 含 `"redis":true`；ask miss→hit。
