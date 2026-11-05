# Day33 Lesson 2 — 带读 docker-compose.yml

services:
  redis:     # 服务名 = 容器 DNS 名
    image: redis:7-alpine
    healthcheck: …   # ping 通才算 healthy

  api:
    build: .         # 用本目录 Dockerfile 构建
    ports: "8033:8000"   # 宿主机:容器内
    environment:
      REDIS_URL: redis://redis:6379/0   # 主机名 redis，不是 127.0.0.1
    depends_on:
      redis:
        condition: service_healthy   # 比「只写 depends_on」更靠谱一点
