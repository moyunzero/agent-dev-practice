# 为 FastAPI 编写 Dockerfile 并成功构建镜像：从菜谱到 curl 通

本地 `uv run uvicorn` 能跑，不代表别人机器、CI、生产环境也能一键复现。  
**容器化**把应用和依赖打进镜像：别人只要有 Docker，就能 `build` / `run` 出同一份服务。

本文按 FastAPI 官方部署思路，写一份最小 **Dockerfile**，`docker build` 成功出镜像，再用 `docker run -p` 映射端口，用 curl 验证 `/health`、`/ask` 与 `/metrics`。

## 你将会得到什么

1. 分清 **镜像 vs 容器**、`build` vs `run`  
2. 读懂 **FROM / COPY / RUN / CMD / EXPOSE**，并知道层缓存为何先拷 `requirements.txt`  
3. 成功构建名为 `day32-fastapi` 的镜像  
4. `docker run -p 宿主机:容器内` 后 curl 通 API  

---

## 零基础名词表

> 建议先读完本节再动手。每个词按：**是什么 → 在本文干什么 → 怎么区分**。

### 镜像（Image）

| 层 | 说明 |
|----|------|
| **是什么** | 打包好的**只读**模板：文件系统层 + 元数据（入口命令等） |
| **在本文干什么** | `docker build -t day32-fastapi .` 的产物；可用 `docker images` 查看 |
| **怎么区分** | 镜像本身**不在跑**；要服务起来必须 `run` 成容器 |

### 容器（Container）

| 层 | 说明 |
|----|------|
| **是什么** | 用镜像启动的**正在运行**的实例（进程 + 可写层） |
| **在本文干什么** | `docker run ... day32-fastapi`；停掉可用 `docker stop` |
| **怎么区分** | 同一镜像可开多个容器；容器删了镜像还在 |

```text
Dockerfile（菜谱）──build──► Image
                              │ run
                              ▼
                         Container ── -p ──► 宿主机可 curl
```

### Dockerfile 与层缓存

| 层 | 说明 |
|----|------|
| **是什么** | 构建镜像的指令列表；每条常对应一层，可缓存 |
| **在本文干什么** | 先 `COPY requirements.txt` + `RUN pip`，再 `COPY app/`，改代码时少重装依赖 |
| **怎么区分** | 改依赖清单会重跑 pip；只改 `app/` 通常只重建最后几层 |

### FROM / COPY / RUN / CMD / EXPOSE

| 指令 | 何时 | 干什么 | 用错会怎样 |
|------|------|--------|------------|
| **FROM** | 构建 | 选基础镜像 | 基础太大/不对 → 体积或缺库 |
| **COPY** | 构建 | 宿主机 → 镜像 | 上下文外的路径拷不进来 |
| **RUN** | **构建时** | 如 `pip install` | 写进镜像；别把「启动命令」误写成 RUN |
| **CMD** | **启动时** | 默认进程 | 容器起来却没服务，多半 CMD 错了 |
| **EXPOSE** | 声明 | 文档性端口 | **不会**自动映射到宿主机 |

### 端口映射 `-p`

| 层 | 说明 |
|----|------|
| **是什么** | `-p 宿主机端口:容器内端口`，把外面的请求转进容器 |
| **在本文干什么** | `-p 8032:8000`：本机 curl `:8032` → 容器内 uvicorn `:8000` |
| **怎么区分** | 左边是你的电脑；右边必须等于容器进程真正监听的端口 |

### 构建上下文（`.`）

| 层 | 说明 |
|----|------|
| **是什么** | `docker build ... .` 末尾目录：发给 Docker 的文件树，`COPY` 只能从这里取 |
| **在本文干什么** | 在含 Dockerfile 的目录执行，`.` = 当前目录 |
| **怎么区分** | 与「Dockerfile 路径 `-f`」不同：上下文决定能拷什么 |

### 与 Compose / 监控栈的关系

| | 本文（Day 级目标） | 常见下一步 |
|--|-------------------|------------|
| 焦点 | **自己写 Dockerfile 并 build 成功** | 多服务 `docker-compose.yml` 一键起栈 |
| 监控 | 镜像内已含 `/metrics`，便于衔接 Prometheus | 把 API 服务写进 Compose 与 Grafana 同网 |

---

## 要解决什么问题

| 只在本机 `uv run` | Docker 镜像 |
|-------------------|-------------|
| 依赖随机器漂移 | 依赖锁进镜像层 |
| 「在我电脑能跑」 | 他人/CI 同一条 `run` |
| 难交给运维 | 标准交付物：镜像名 + 端口说明 |

---

## 环境准备（从零开始）

- 已安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（或 Docker Engine）  
- 终端能执行 `docker version`  

官方参考：[Docker for FastAPI](https://fastapi.tiangolo.com/deployment/docker/)、[Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)。

---

## 完整代码

在空目录创建如下文件。

### `requirements.txt`

```text
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
prometheus-fastapi-instrumentator>=7.0.0
```

### `app/main_api.py`

```python
from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(title="day32-docker")
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

CACHE_LOOKUPS = Counter(
    "cache_lookups_total",
    "Ask answer cache lookups",
    labelnames=("result",),
)
_ANSWER_CACHE: dict[str, str] = {}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/ask")
async def ask(q: str = "hi") -> dict:
    if q in _ANSWER_CACHE:
        CACHE_LOOKUPS.labels(result="hit").inc()
        return {"q": q, "answer": _ANSWER_CACHE[q], "cache": "hit"}
    CACHE_LOOKUPS.labels(result="miss").inc()
    await asyncio.sleep(0.05)
    answer = f"echo:{q}"
    _ANSWER_CACHE[q] = answer
    return {"q": q, "answer": answer, "cache": "miss"}


@app.get("/fail")
async def fail() -> dict:
    raise HTTPException(status_code=500, detail="boom")
```

另加空文件 `app/__init__.py`。

### `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main_api:app", "--host", "0.0.0.0", "--port", "8000"]
```

国内若拉不动 Docker Hub，可将 `FROM` 换成镜像站提供的 `python:3.12-slim` 等价地址；`pip` 也可设国内 index。

### `.dockerignore`（建议）

```text
.venv
__pycache__
*.pyc
```

---

## 这段 Dockerfile 在干什么

1. **FROM** 轻量 Python 底包  
2. **先 COPY requirements + RUN pip**：依赖层可缓存  
3. **再 COPY app/**：改业务代码不必重装包  
4. **CMD**：监听 `0.0.0.0:8000`（只绑 `127.0.0.1` 时端口映射进不来）  

---

## 启动与验证

**构建镜像：**

```bash
docker build -t day32-fastapi .
docker images | grep day32-fastapi
```

**期望**：出现 `day32-fastapi` 仓库名。

**运行并验收：**

```bash
docker run --rm -d --name day32-api -p 8032:8000 day32-fastapi

curl -s http://127.0.0.1:8032/health
curl -s 'http://127.0.0.1:8032/ask?q=hello'
curl -s http://127.0.0.1:8032/metrics | head
```

**期望**：`{"status":"ok"}`；ask 返回 JSON；metrics 含 Prometheus 文本。

**停止：**

```bash
docker stop day32-api
```

若提示容器名已占用：先 `docker stop day32-api`（或 `docker rm -f day32-api`）再 run。

---

## 踩过的坑

### 1. 只有 EXPOSE，宿主机 curl 不通

**原因**：EXPOSE 不映射端口。  
**处理**：加 `-p 宿主机:容器内`。

### 2. `-p 8032:8032` 但进程听 8000

**现象**：连接失败或空。  
**处理**：右边必须等于容器内真实端口（本文 `8000`）。

### 3. CMD 使用 `--host 127.0.0.1`

**现象**：映射后仍访问不到。  
**处理**：使用 `0.0.0.0`。

### 4. 每次改一行代码都全量 pip

**原因**：先 COPY 了整个项目再 RUN pip。  
**处理**：requirements 与 app 分两步 COPY。

---

## 取舍与未做之事

| 做了 | 故意没做 |
|------|----------|
| 单服务 Dockerfile + build + run | 多服务 Compose 整栈（常见下一主题） |
| 含 `/metrics` 便于衔接监控 | 多阶段构建、非 root 用户硬化（可后续加） |
| 层缓存友好的 COPY 顺序 | 推送到远端 Registry |

---

## 小结

- **build → 镜像，run → 容器**；Dockerfile 是菜谱。  
- **RUN 构建时，CMD 启动时**；**`-p` 左边宿主机、右边容器内**。  
- 验收：`docker images` 有名 + curl 映射端口通。  

下一步常把 API 与 Redis / 向量库等写进 **Compose**，一键起整个应用栈——单镜像已经就位。

---

*系列笔记 · Agent 工程跟练 · Week 5 Day 32*
