# Day33 Lesson 1 — Compose 地图（先读再答）

```text
docker-compose.yml
  services:
    api:    → 容器 A（FastAPI，build 自 Day32 Dockerfile）
    redis:  → 容器 B（官方 redis 镜像）
  默认同一 Docker network
       api 用主机名 "redis" 访问 B:6379
```

## 和 Day32 单容器的差别

| | `docker run`（Day32） | Compose（Day33） |
|--|----------------------|------------------|
| 服务数 | 通常 1 个 | **多个**一起声明 |
| 启动 | 每条命令敲一遍 | **`docker compose up` 一键** |
| 互访 | 要自己建网/写 IP | **服务名 = DNS 名** |
| 配置 | 散落在命令行 | 集中在 **yml** |

## 关键词

| 词 | 是什么 |
|----|--------|
| **service** | yml 里声明的一个容器角色（api / redis） |
| **image / build** | 直接拉镜像，或用 Dockerfile 现场 build |
| **ports** | 映射到宿主机（给浏览器 curl） |
| **depends_on** | 启动**顺序**（先起 redis 再起 api）；**不保证** Redis 已就绪可连 |
| **environment** | 注入环境变量（如 `REDIS_URL=redis://redis:6379/0`） |

## 易混

- Compose ≠ K8s；今天只管本机多容器编排。  
- `depends_on` ≠ 健康检查通过；复杂场景才加 `healthcheck`。  
- 容器内访问 Redis 用 **`redis:6379`**，不是 `127.0.0.1`（那是容器自己）。

---

读完后回答抽问。本课**先不起栈**。
