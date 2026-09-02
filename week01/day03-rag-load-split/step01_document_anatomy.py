"""第 1 课：先搞懂 Document 长什么样（加载 ≠ 分块）。"""

from pathlib import Path

from langchain_community.document_loaders import TextLoader

MD = Path(__file__).parent / "data" / "sample.md"
TXT = Path(__file__).parent / "data" / "sample_plain.txt"


def inspect(label: str, path: Path) -> None:
    docs = TextLoader(str(path), encoding="utf-8").load()
    doc = docs[0]
    print(f"\n--- {label} ---")
    print(f"Document 个数: {len(docs)}")
    print(f"metadata: {doc.metadata}")
    print(f"page_content 长度: {len(doc.page_content)} 字符")
    print(f"正文前 120 字:\n{doc.page_content[:120]}...")


def main() -> None:
    print("Loader 的工作：文件 → List[Document]")
    print("此时还没有 chunk，整文件通常就是 1 个 Document。\n")
    inspect("Markdown 文件 (sample.md)", MD)
    inspect("纯文本文件 (sample_plain.txt)", TXT)
    print(
        """

【本课要点】
1. RAG 第一步是 Loader，不是 Splitter。
2. Document = page_content（正文）+ metadata（来源）。
3. TextLoader 对 .md / .txt 都是「读成字符串」——MD 的 # 标题不会自动变成结构，只是字符。
"""
    )


if __name__ == "__main__":
    main()
