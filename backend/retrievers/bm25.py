"""BM25 keyword retriever — in-memory Okapi BM25 with Chinese tokenization.

Uses the rank_bm25 library (BM25Okapi) instead of a hand-written TF-IDF cosine
implementation. BM25 rewards rare query terms (high IDF, e.g. "车险") and applies
length normalisation via average document length, which significantly improves
keyword discrimination compared to plain TF-IDF cosine similarity.
"""
from __future__ import annotations

from typing import Any

from rank_bm25 import BM25Okapi

from ..config import get_settings

_jieba_available = False
try:
    import jieba
    _jieba_available = True
except ImportError:
    pass


def _tokenize_chinese(text: str) -> list[str]:
    if _jieba_available:
        tokens = jieba.lcut(text)
        return [t.strip().lower() for t in tokens if t.strip()]
    chars = [c for c in text if '\u4e00' <= c <= '\u9fff']
    bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)] if len(chars) >= 2 else []
    return bigrams or chars


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for seg in text.split():
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in seg)
        if has_chinese:
            chinese_part = ''.join(c for c in seg if '\u4e00' <= c <= '\u9fff')
            tokens.extend(_tokenize_chinese(chinese_part))
            non_chinese = ''.join(c for c in seg if not '\u4e00' <= c <= '\u9fff')
            if non_chinese:
                tokens.append(non_chinese.lower())
        else:
            tokens.append(seg.lower())
    return tokens


class BM25Retriever:
    """In-memory keyword retriever using Okapi BM25.

    Documents are loaded from VectorRetriever on first init and cached at class level
    so that all instances share the same index.
    """

    _shared_index: dict[str, Any] | None = None
    _shared_docs: list[dict] = []
    _initialized: bool = False

    def __init__(self) -> None:
        pass

    def _initialize(self) -> None:
        if BM25Retriever._initialized:
            return

        try:
            from .vector import VectorRetriever
            vr = VectorRetriever()
            BM25Retriever._shared_docs = vr.get_all_documents()

            if not BM25Retriever._shared_docs:
                BM25Retriever._shared_index = None
                BM25Retriever._initialized = True
                return

            corpus: list[list[str]] = [
                _tokenize(d.get("content", "")) for d in BM25Retriever._shared_docs
            ]
            BM25Retriever._shared_index = {
                "bm25": BM25Okapi(corpus, k1=1.5, b=0.75),
            }
            BM25Retriever._initialized = True

        except Exception:
            BM25Retriever._initialized = True

    def retrieve(self, query: str, top_k: int = 20) -> list[dict]:
        self._initialize()

        if not BM25Retriever._shared_index or not BM25Retriever._shared_docs:
            return []

        bm25: BM25Okapi = BM25Retriever._shared_index["bm25"]

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = bm25.get_scores(query_tokens)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        results: list[dict] = []
        for idx in ranked_indices:
            if scores[idx] <= 0:
                continue
            d = dict(BM25Retriever._shared_docs[idx])
            d["score"] = float(scores[idx])
            results.append(d)

        return results

    def refresh(self) -> None:
        BM25Retriever._initialized = False
        BM25Retriever._shared_index = None
        BM25Retriever._shared_docs = []
