# Day48–51 Lesson 1 — 把客服 API 打进镜像（Compose 里当 api 服务）
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app_main.py faq_search.py ./
COPY faq/ ./faq/

EXPOSE 8000

CMD ["uvicorn", "app_main:app", "--host", "0.0.0.0", "--port", "8000"]
