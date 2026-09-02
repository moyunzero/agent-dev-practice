# Week 1 / Day 7 — Docker 打包 Naive RAG

> **状态**：`available`  
> **长文教程**（可选）：[用 Docker 打包 Naive RAG 文档问答 API](../../notes/week01/day07-docker.md)

## 今日目标

把 Day 5–6 的 Naive RAG API 打进 Docker 镜像，容器内 `/health` 与 `POST /ask` 可复现。

## 前置

- 本地已跑通 Day 5–6（建议先在本机 `uv sync` 过一次，HF embedding 缓存到 `~/.cache/huggingface`）
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) 已安装
- 宿主机 Ollama 运行中（容器通过 `host.docker.internal` 访问）

## 文件说明

| 文件 | 作用 |
|------|------|
| `Dockerfile` | **本日唯一源码**：基于 `python:3.12-slim`，复制 `day05-06-naive-rag` 并 `uvicorn` 启动 |
| （构建上下文）`../day05-06-naive-rag/` | 被 COPY 进镜像的应用代码、`chroma_db`、依赖锁 |

> 本目录没有 Python 脚本；所有运行逻辑在 `week01/day05-06-naive-rag/`。

## 推荐顺序

| 步骤 | 做什么 |
|:----:|--------|
| 0 | 确认 Day 5–6 本机验收通过 |
| 1 | 在**仓库根目录**执行 `docker build`（见下方命令） |
| 2 | `docker run` 挂载 HF 缓存 + 映射 8002 |
| 3 | `curl /health` 与 `curl /ask` 验收 |
| 4 | 理解：镜像内 Ollama 走宿主机、embedding 走挂载缓存 |

## 验收命令（汇总）

```bash
# 在仓库根目录 agent-dev-practice/ 执行
docker build \
  -f week01/day07-docker/Dockerfile \
  -t naive-rag \
  week01/day05-06-naive-rag

docker run -d --name naive-rag \
  -p 8002:8002 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  naive-rag

curl -s http://127.0.0.1:8002/health
curl -s -X POST http://127.0.0.1:8002/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"chunk_overlap 是干什么的？"}'
```

## 验收标准

- 容器 `healthy` 或 `/health` 返回 ok
- `/ask` 与宿主机直跑 Day 5–6 结果一致
- 能解释为什么挂载 `~/.cache/huggingface`

## 备注

**国内网络**：Dockerfile 使用 DaoCloud 代理 `python:3.12-slim`；embedding 模型依赖宿主机 HF 缓存。

## 收工清理

```bash
docker stop naive-rag && docker rm naive-rag
# 镜像 naive-rag 可按需 docker rmi
```
