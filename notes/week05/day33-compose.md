# 用 Docker Compose 一键启动 FastAPI + Redis 应用栈

Day32 已经会用 Dockerfile 打出单个 FastAPI 镜像。真实系统很少只有一个容器——至少还有缓存、数据库、向量库。  
若每个服务都手敲 `docker run`，端口、网络、环境变量很容易散架。

**Docker Compose** 用一份 `docker-compose.yml` 声明多个 **service**，一条 `docker compose up` 起整栈；同一网络上用**服务名当 DNS** 互访。

本文落地：**FastAPI + Redis** 最小可运行栈（对齐「一键启动整个应用栈」；原文手撕中的 Milvus 可作为加码，不阻塞当日闭环）。

## 你将会得到什么

1. 分清 Compose 相对多次 `docker run` 多解决了什么  
2. 写好含 `api` / `redis` 的 `docker-compose.yml`，并 `up` 成功  
3. 用 `/health` 与两次 `/ask` 证明 **跨容器真连通**（不只看 `ps` 发绿）  
4. 说清 `depends_on`：**顺序 ≠ 就绪**  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### Docker Compose

| 层 | 说明 |
|----|------|
| **是什么** | 多容器编排工具：用 YAML 声明服务、网络、卷，统一起停 |
| **在本文干什么** | 一键起 FastAPI（自建镜像）+ Redis（官方镜像） |
| **怎么区分** | 不是 K8s；只管本机/单机编排。也不同于「只 build 一个 Dockerfile」 |

```text
docker-compose.yml
  services:
    redis  ──官方镜像──► 容器 B :6379
    api    ──build .  ──► 容器 A :8000
         REDIS_URL=redis://redis:6379/0
宿主机 curl :8033 ──ports──► api:8000
```

### service（服务）

| 层 | 说明 |
|----|------|
| **是什么** | yml 里一个逻辑角色，通常对应一个容器定义 |
| **在本文干什么** | `api`、`redis` 两个 service |
| **怎么区分** | 服务名会出现在容器名前缀，更重要的是作 **DNS 名** |

### 服务名 = DNS

| 层 | 说明 |
|----|------|
| **是什么** | Compose 默认网络上，服务名可被其它容器解析 |
| **在本文干什么** | API 用 `redis://redis:6379/0`，主机名就是服务名 `redis` |
| **怎么区分** | 容器内 `127.0.0.1` = **自己**；连隔壁服务必须用服务名（或容器 IP） |

### `build` vs `image`

| 字段 | 干什么 |
|------|--------|
| **`image:`** | 直接使用已有镜像（本文 Redis：`redis:7-alpine`） |
| **`build:`** | 用指定目录 Dockerfile **现场构建**（本文 api：`build: .`） |

### `ports` / `environment` / `depends_on`

| 字段 | 是什么 | 注意 |
|------|--------|------|
| **ports** | 宿主机↔容器端口映射 | 只给需要从本机 curl 的服务 |
| **environment** | 注入环境变量 | `REDIS_URL` 指向服务名 |
| **depends_on** | 控制**启动顺序** | **不保证**依赖已可连接 |

### 就绪（ready）与 healthcheck

| 层 | 说明 |
|----|------|
| **是什么** | 进程 Up ≠ 端口可连 ≠ 应用 ping 通 |
| **在本文干什么** | Redis 配 `healthcheck`；api `depends_on` 使用 `condition: service_healthy`；再用 `/health` 做应用层验收 |
| **怎么区分** | `compose ps` 绿 ≠ 业务连通；以 curl 结果为准 |

### 与 Day32 的关系

| Day32 | Day33 |
|-------|-------|
| 单个镜像 build + run | **多服务**编排 + 一键起停 |
| `-p` 映射一个 API | yml 里声明 api + redis，服务名互访 |

---

## 要解决什么问题

| 多次 `docker run` | Compose |
|-------------------|---------|
| 命令长、易忘 | 一份 yml |
| 手搓网络/IP | 服务名 DNS |
| 难复现给同事 | `compose up` 即文档 |

---

## 环境准备（从零开始）

- Docker Desktop（或 Engine + Compose 插件）  
- 空出端口：**8033**（API）、可选 **6389**（Redis 宿主机调试）  

官方：[Docker Compose](https://docs.docker.com/compose/)。

---

## 完整代码

### `requirements.txt`

```text
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
prometheus-fastapi-instrumentator>=7.0.0
redis>=5.0.0
```

### `app/main_api.py`（节选逻辑）

```python
import os
from fastapi import FastAPI
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")

def _redis():
    return redis.Redis.from_url(REDIS_URL, decode_responses=True)

@app.get("/health")
async def health():
    try:
        _redis().ping()
        return {"status": "ok", "redis": True}
    except Exception as e:
        return {"status": "degraded", "redis": False, "error": str(e)}

@app.get("/ask")
async def ask(q: str = "hi"):
    r = _redis()
    key = f"ask:{q}"
    cached = r.get(key)
    if cached is not None:
        return {"q": q, "answer": cached, "cache": "hit"}
    answer = f"echo:{q}"
    r.set(key, answer)
    return {"q": q, "answer": answer, "cache": "miss"}
```

（完整文件可含 Instrumentator `/metrics`；结构同上。）

### `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main_api:app", "--host", "0.0.0.0", "--port", "8000"]
```

### `docker-compose.yml`

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6389:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  api:
    build: .
    ports:
      - "8033:8000"
    environment:
      REDIS_URL: redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
```

---

## 这段配置在干什么

1. **redis**：拉官方镜像；healthcheck 用 `PING`  
2. **api**：build 本地 Dockerfile；`REDIS_URL` 主机名为 **`redis`**  
3. **depends_on + service_healthy**：尽量等 Redis 可 ping 再起 api  
4. **8033:8000**：本机验收入口  

---

## 启动与验证

```bash
docker compose up -d --build
docker compose ps
```

**期望**：`redis` healthy，`api` Up。

```bash
curl -s http://127.0.0.1:8033/health
curl -s 'http://127.0.0.1:8033/ask?q=hello'
curl -s 'http://127.0.0.1:8033/ask?q=hello'
```

**期望**：

- `"status":"ok","redis":true`  
- 第一次 `"cache":"miss"`，第二次 `"cache":"hit"`  

停栈：

```bash
docker compose down
```

---

## 踩过的坑

### 1. `REDIS_URL` 写成 `127.0.0.1`

**现象**：health 里 `redis: false`。  
**原因**：127.0.0.1 是 api 容器自己。  
**处理**：用服务名 `redis`。

### 2. 只看 `compose ps` 就宣称成功

**现象**：容器绿但业务连不上。  
**处理**：必须以 `/health` 与缓存 hit/miss 验收。

### 3. 端口占用（6389 / 8033）

**处理**：改 yml 宿主机端口，或去掉 redis 的 `ports`（仅容器网内访问即可）。

### 4. 以为 `depends_on` 等于「一定连得上」

**口诀**：**顺序 ≠ 就绪**；配 healthcheck + 应用层检查。

---

## 取舍与未做之事

| 做了 | 故意没做 |
|------|----------|
| FastAPI + Redis 一键栈 | 当日强制 Milvus 三件套（磁盘/时间；可作加码） |
| 服务名 DNS + health 验收 | K8s、生产密钥、完整监控 Compose 合并 |
| `compose up/down` | 多环境 override 文件深挖 |

原文手撕提到 FastAPI + Milvus + Redis：模式相同——再加一个 `milvus` service 与依赖即可；先把双服务编排跑通更重要。

---

## 小结

- Compose = **多服务声明 + 一键起停 + 服务名互访**。  
- **`redis` 是 DNS 名**；`build` 自建、`image` 现成。  
- **`depends_on` 管顺序，不管就绪**；用 health + `/health` curl 验收。  
- 起：`docker compose up -d --build`；停：`docker compose down`。  

下一步常见是把日志打成 **JSON**，为接入 ELK 做准备——栈已经能一键起，可观测与部署主线继续收口。

---

*系列笔记 · Agent 工程跟练 · Week 5 Day 33*
