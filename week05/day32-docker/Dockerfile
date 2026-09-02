# Day32 — FastAPI Dockerfile（上游：编写并成功构建镜像）
# 构建（在本目录执行）：
#   docker build -t day32-fastapi .
#
# 国内网络若拉不动 Docker Hub，可把 FROM 换成：
#   docker.m.daocloud.io/library/python:3.12-slim

FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ ./app/

EXPOSE 8000

CMD ["uvicorn", "app.main_api:app", "--host", "0.0.0.0", "--port", "8000"]
