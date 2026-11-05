"""Day14 Milvus 连接配置。"""

import os

MILVUS_HOST = os.getenv("MILVUS_HOST", "127.0.0.1")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19531")
MILVUS_URI = os.getenv("MILVUS_URI", f"http://{MILVUS_HOST}:{MILVUS_PORT}")

COLLECTION = "day14_rag_upgrade"
DIM = 384
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
