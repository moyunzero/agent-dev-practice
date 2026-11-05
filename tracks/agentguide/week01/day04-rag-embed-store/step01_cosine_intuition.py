"""第 1 课：余弦相似度直觉（Embedding 检索的数学基础，无需模型）。"""

import math


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)


def main() -> None:
    # 想象三维空间里，语义相近的词向量方向接近（真实 embedding 是高维，原理相同）
    cat = [1.0, 0.9, 0.1]       # 「猫」
    dog = [0.95, 0.85, 0.15]    # 「狗」—— 和猫接近
    car = [0.1, 0.2, 0.95]      # 「汽车」—— 和猫较远

    print("余弦相似度（越接近 1 越相似）：")
    print(f"  猫 vs 狗: {cosine_similarity(cat, dog):.3f}")
    print(f"  猫 vs 汽车: {cosine_similarity(cat, car):.3f}")

    query = [0.98, 0.88, 0.12]  # 「宠物」—— 更接近猫/狗那一簇
    docs = [("关于猫的文章", cat), ("关于狗的文章", dog), ("关于汽车的文章", car)]
    print("\n问句「宠物」与各文档的相似度：")
    for title, vec in docs:
        score = cosine_similarity(query, vec)
        print(f"  {score:.3f}  {title}")

    print(
        """

【本课要点】
1. RAG 检索靠「向量相似度」，不是 Ctrl+F 搜关键字。
2. Embedding 模型把文本变成高维向量；语义近 → 向量方向近 → 余弦相似度高。
3. Day4 后面：用真实模型 embed chunk，用向量库存起来，问句 embed 后找 Top-K 最相似的 chunk。
"""
    )


if __name__ == "__main__":
    main()
