# Day32 Lesson 1 — 镜像 / 容器 / Dockerfile 地图

```text
Dockerfile（菜谱）
    │ docker build
    ▼
镜像 Image（只读模板，可有多层）
    │ docker run
    ▼
容器 Container（跑起来的进程 + 可写层）
    │ -p 宿主机:容器内
    ▼
curl http://127.0.0.1:宿主机端口/...
```

## 易混对照

| 概念 | 是什么 | 类比 |
|------|--------|------|
| **镜像** | 打包好的只读文件系统 + 元数据 | 安装盘 / 快照 |
| **容器** | 用镜像启动的**正在跑**的实例 | 装好并开机的那一台 |
| **层 (layer)** | Dockerfile 每条会留下的缓存层 | 叠罗汉；改上面一层下面可复用 |

## Dockerfile 常用指令（本课会用到）

| 指令 | 干什么 |
|------|--------|
| `FROM` | 选基础镜像（如 `python:3.12-slim`） |
| `WORKDIR` | 容器内工作目录 |
| `COPY` | 把宿主机文件拷进镜像 |
| `RUN` | **构建时**执行（如 `pip install`） |
| `EXPOSE` | 文档性声明容器内监听端口（不自动开宿主机端口） |
| `CMD` | **启动容器时**默认命令（如 `uvicorn ...`） |

## 和 Day7 / Day31 的关系

| | Day7 | Day31 | Day32 |
|--|------|-------|-------|
| 重点 | 把 RAG API 打进镜像 | Compose 起监控栈 | **再写/再 build** FastAPI 镜像（Week5 语境） |

Day31 的 `docker compose` 用的是别人的镜像；今天是**自己写 Dockerfile 并 build**。

---

读完后回答教练抽问。本课**先不 build**。
