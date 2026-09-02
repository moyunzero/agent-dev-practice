"""研究助手两个工具：本地 RAG + 网页搜索。"""

from __future__ import annotations

from langchain.tools import tool

from rag_store import search_kb


@tool
def search_knowledge_base(query: str) -> str:
    """检索本地内部知识库（Nebula Router / N7-2026 等私有笔记）。
    问内部协议、桶数、超时、负责人时优先用本工具。"""
    return search_kb(query)


@tool
def web_search(query: str) -> str:
    """搜索公开网页（DuckDuckGo）。问新闻、通用概念、公网资料时用本工具。
    不要用它查 Nebula 内部协议（公网没有）。"""
    try:
        from ddgs import DDGS

        rows = list(DDGS().text(query, max_results=3))
    except Exception as e:  # noqa: BLE001 — 教学：网络失败要有可读返回
        return f"网页搜索失败（可离线重试或换网络）：{e}"

    if not rows:
        return "网页搜索无结果。"
    parts = []
    for i, r in enumerate(rows, 1):
        title = r.get("title") or ""
        body = r.get("body") or r.get("href") or ""
        href = r.get("href") or ""
        parts.append(f"[{i}] {title}\n{body}\n来源: {href}")
    return "\n\n".join(parts)
