"""Milvus 连接配置 — 后续脚本共用。"""

import os

MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19531")
MILVUS_URI = os.getenv("MILVUS_URI", f"http://{MILVUS_HOST}:{MILVUS_PORT}")

COLLECTION = "day12_rag_demo"
DIM = 384  # all-MiniLM-L6-v2，与 Week1 一致
