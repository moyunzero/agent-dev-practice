"""FAQ 模糊检索（规范化 + bigram；关键词命中加分。可换成 Day4 Chroma）。"""

from __future__ import annotations

import re
from pathlib import Path

FAQ_DIR = Path(__file__).resolve().parent / "faq"
MIN_SCORE = 0.2

# 问句/文档里出现这些词，直接抬高对应片段（政策类常见说法）
BOOST_KEYWORDS = ("退货", "退款", "7天", "无理由", "包邮", "运费", "发货")


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"\s+", "", s)
    s = s.replace("七天", "7天")
    return s


def _bigram_score(query: str, text: str) -> float:
    q = _norm(query)
    t = _norm(text)
    if len(q) < 2:
        return 1.0 if q and q in t else 0.0
    hits = 0
    total = 0
    for i in range(len(q) - 1):
        bg = q[i : i + 2]
        total += 1
        if bg in t:
            hits += 1
    return hits / total if total else 0.0


def load_chunks() -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    for path in sorted(FAQ_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8").strip()
        for block in raw.split("\n\n"):
            block = block.strip()
            if block and not block.startswith("#"):
                chunks.append({"doc_id": path.name, "text": block})
    return chunks


def search_faq(query: str, *, min_score: float = MIN_SCORE) -> dict | None:
    """返回最佳片段；不够置信则 None。"""
    qn = _norm(query)
    best: dict | None = None
    best_score = -1.0
    for chunk in load_chunks():
        score = _bigram_score(query, chunk["text"])
        tn = _norm(chunk["text"])
        for kw in BOOST_KEYWORDS:
            if kw in qn and kw in tn:
                score = max(score, 0.55)
        if score > best_score:
            best_score = score
            best = {**chunk, "score": round(score, 4)}
    if best is None or best_score < min_score:
        return None
    return best
