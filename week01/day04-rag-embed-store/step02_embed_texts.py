"""第 2 课：用真实 Embedding 模型把文本变成向量，并比较相似度。"""

from sentence_transformers import SentenceTransformer
from sentence_transformers.util import cos_sim

# 小模型，首次运行会自动下载（约 80MB）
MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def main() -> None:
    print(f"加载模型: {MODEL}（首次可能需下载）\n")
    model = SentenceTransformer(MODEL)

    texts = [
        "FastAPI 是一个 Python Web 框架，用于构建 API。",
        "FastAPI 基于类型注解，能自动生成 OpenAPI 文档。",
        "今天天气很好，适合出去散步。",
    ]
    labels = ["A-框架定义", "B-相关功能", "C-无关话题"]

    embeddings = model.encode(texts)
    print(f"每条文本 → 向量维度: {embeddings.shape[1]}\n")

    query = "FastAPI 怎么用来写接口？"
    query_vec = model.encode(query)

    print(f"问句: {query}\n")
    print("与各句的余弦相似度（越高越相关）：")
    scores = cos_sim(query_vec, embeddings)[0]
    ranked = sorted(zip(labels, texts, scores), key=lambda x: x[2], reverse=True)
    for label, text, score in ranked:
        print(f"  {score:.3f}  [{label}] {text}")

    print(
        """

【本课要点】
1. 同一个 Embedding 模型：chunk 入库时 embed 一次，问句检索时再 embed 一次。
2. A、B 与问句都是 FastAPI 相关 → 相似度应高于 C。
3. 向量维度由模型决定（本模型 384 维），与文本长度无关。
"""
    )


if __name__ == "__main__":
    main()
