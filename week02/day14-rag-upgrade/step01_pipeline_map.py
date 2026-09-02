"""第 1 课：Week1 Naive RAG vs Day14 升级流水线对照（不连库）。"""

from __future__ import annotations


def main() -> None:
    print("=== Day14 第 1 课：系统升级地图 ===\n")
    print("上游目标：将第一周的 RAG 系统升级，集成混合检索、Reranker 和 Milvus\n")

    print("【Week1 Naive RAG · Day5–6】")
    print(
        """
  文档(MD)
    → Splitter
    → Embed (all-MiniLM-L6-v2, 384)
    → Chroma（本地文件）
    → 仅向量 similarity_search Top-K
    → Prompt + Ollama → answer
"""
    )

    print("【Day14 升级 RAG】三处替换/插入")
    print(
        """
  文档(MD)
    → Splitter                         （Day3，不变）
    → Embed                            （Day4，不变）
    → ★ Milvus Standalone              （Day12，替换 Chroma）
         ↘
  问句 → ★ BM25(chunk 文本)             （Day9）
       → ★ Milvus 向量 Top-N
       → ★ RRF 融合
       → ★ CrossEncoder Rerank         （Day9）
       → Prompt + Ollama → answer      （Day5–6）
"""
    )

    print("对照表：")
    rows = [
        ("向量库", "Chroma", "Milvus（独立 Docker 服务）"),
        ("召回", "仅向量", "BM25 + 向量 → RRF"),
        ("排序", "Top-K 即最终", "Rerank 精排后再取 FINAL_K"),
        ("生成", "Ollama", "同左（可选演示）"),
    ]
    print(f"  {'环节':<8} {'Week1':<14} {'Day14'}")
    print("  " + "-" * 52)
    for a, b, c in rows:
        print(f"  {a:<8} {b:<14} {c}")

    print(
        """
【本课要点】
1. 升级不是推倒重来：Loader/Split/Embed/生成大多复用。
2. 强制三项：Milvus + 混合检索 + Reranker（对应上游目标原文）。
3. 下节课：起 Milvus，把 chunk 向量写入 collection。

抽问：
Q1. 三处升级分别是什么？
Q2. 为什么 BM25 不能只靠 Milvus？
Q3. Rerank 插在混合召回的前面还是后面？为什么？
"""
    )


if __name__ == "__main__":
    main()
