# Day32 Lesson 2 — 带读 Dockerfile

自上而下读：

1. FROM python:3.12-slim     → 基础环境
2. WORKDIR /app             → 容器内工作目录
3. COPY requirements.txt    → 先拷依赖清单（利于层缓存）
4. RUN pip install …        → **构建时**装依赖
5. COPY app/                → 再拷业务代码
6. EXPOSE 8000              → 声明容器内端口（文档性）
7. CMD uvicorn …            → **启动时**跑 API，监听 0.0.0.0:8000

为何 `--host 0.0.0.0`：只绑 127.0.0.1 时，容器外（含端口映射）访问不到。
