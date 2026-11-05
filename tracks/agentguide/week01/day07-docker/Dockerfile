# Week1 Day7 — 将 day05-06 Naive RAG 打成可运行镜像
# 构建命令（在仓库根目录执行）：
#   docker build -f week01/day07-docker/Dockerfile -t naive-rag week01/day05-06-naive-rag
#
# 国内网络：FROM 使用 DaoCloud 代理 Docker Hub；海外可改回 python:3.12-slim

FROM docker.m.daocloud.io/library/python:3.12-slim

WORKDIR /app

# PyPI / HuggingFace 国内加速（构建阶段下载依赖与 embedding 模型）
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    HF_ENDPOINT=https://hf-mirror.com

# sentence-transformers / chromadb 编译依赖
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

# 先只复制依赖清单 → 利用 Docker 层缓存（改代码不必重装依赖）
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# 再复制应用代码与已建好的向量索引
COPY main.py demo_rag_chain.py ./
COPY data/ data/
COPY chroma_db/ chroma_db/

# embedding 模型在运行时加载；docker run 时挂载宿主机缓存（见 LEARN.md 第 4 课）
# 本地已跑过 demo_rag_chain.py 则 ~/.cache/huggingface 里通常已有 all-MiniLM-L6-v2

# 默认连宿主机 Ollama（macOS Docker Desktop）
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
    OLLAMA_MODEL=qwen2:7b

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
