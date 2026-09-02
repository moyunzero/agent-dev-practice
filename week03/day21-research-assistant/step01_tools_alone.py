"""第 1 课：两个工具各自能工作（不经过 Agent）。"""

from __future__ import annotations

from rag_store import get_vectorstore, search_kb
from research_tools import web_search


def main() -> None:
    print("=== 建索引（首次会下载 embedding 模型，稍等）===\n")
    get_vectorstore(rebuild=True)
    print("索引就绪：data/nebula_notes.md → chroma_db/\n")

    q_kb = "Nebula Router 协议版本和桶数是多少？"
    print(f"--- A. 本地知识库 ---\nQ: {q_kb}\n")
    print(search_kb(q_kb))
    print()

    q_web = "What is DuckDuckGo"
    print(f"--- B. 网页搜索 ---\nQ: {q_web}\n")
    print(web_search.invoke({"query": q_web}))
    print("\n要点：RAG=本地私有笔记；Web=公网。研究助手要把两者都挂给 Agent。")


if __name__ == "__main__":
    main()
