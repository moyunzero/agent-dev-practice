# Week 5 / Day 32 — FastAPI Dockerfile

> **状态**：`available`  
> **长文教程**（可选）：[为 FastAPI 编写 Dockerfile 并成功构建镜像](../../notes/week05/day32-docker.md)

## 今日目标

为 FastAPI 编写 Dockerfile，成功构建镜像，并用 `docker run -p` + curl 验证。

## 前置

- Docker Desktop  
- 本课宿主机端口 **8032** → 容器内 **8000**

## 文件说明

| 文件 | 作用 |
|------|------|
| `Dockerfile` | 构建菜谱 |
| `requirements.txt` | pip 依赖 |
| `app/main_api.py` | FastAPI + `/metrics` |
| `lesson01_docker_map.md` 等 | 课内讲义 |

## 推荐顺序

| 步骤 | 命令 | 说明 |
|:----:|------|------|
| 1 | 读 `lesson01_docker_map.md` | 镜像/容器 |
| 2 | `docker build -t day32-fastapi .` | 构建 |
| 3 | `docker run --rm -d --name day32-api -p 8032:8000 day32-fastapi` | 运行 |
| 4 | curl `/health` `/ask` `/metrics` | 验收 |
| 5 | `docker stop day32-api` | 收工 |

## 验收命令（汇总）

```bash
cd week05/day32-docker
docker build -t day32-fastapi .
docker images | rg day32-fastapi

docker run --rm -d --name day32-api -p 8032:8000 day32-fastapi
curl -s http://127.0.0.1:8032/health
curl -s 'http://127.0.0.1:8032/ask?q=hello'
curl -s http://127.0.0.1:8032/metrics | head
docker stop day32-api
```

**期望**：镜像列表有 `day32-fastapi`；health/ask/metrics 有预期响应。
