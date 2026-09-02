# Week 1 / Day 7 — Docker 打包 Naive RAG

> **状态**：`available`
> 对外文章：[用 Docker 打包 Naive RAG 文档问答 API](../../notes/week01/day07-docker.md)

## 怎么学

按文章自学；不要一次跑完全部 Docker 命令。

## 验收命令

```bash
# 构建（仓库根目录）
docker build \
  -f week01/day07-docker/Dockerfile \
  -t naive-rag \
  week01/day05-06-naive-rag

# 运行（挂载本机 HuggingFace 缓存 + 映射端口）
docker run -d --name naive-rag \
  -p 8002:8002 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  naive-rag

# 验证
curl -s http://127.0.0.1:8002/health
curl -s -X POST http://127.0.0.1:8002/ask \
  -H "Content-Type: application/json" \
  -d '{"question":"chunk_overlap 是干什么的？"}'
```

**国内网络**：Dockerfile 已用 DaoCloud 代理 `python:3.12-slim`；embedding 模型通过挂载 `~/.cache/huggingface` 复用本机缓存（需先本地跑过 Day5–6）。
