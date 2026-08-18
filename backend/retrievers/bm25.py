"""BM25 keyword retriever — uses rank-bm25 for in-memory BM25 scoring."""
from __future__ import annotations

from typing import Any

from ..config import get_settings


class BM25Retriever:
    """In-memory BM25 retriever.

    Documents are loaded from Milvus on first init and cached.
    For production with >100k docs, consider Elasticsearch instead.
    """

    def __init__(self) -> None:
        self._bm25: Any = None
        self._docs: list[dict] = []
        self._initialized = False

    def _initialize(self) -> None:
        """Load all docs from Chroma and build BM25 index."""
        if self._initialized:
            return

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            raise RuntimeError("rank-bm25 is not installed. Run: pip install rank-bm25")

        try:
            from .vector import VectorRetriever
            vr = VectorRetriever()
            self._docs = vr.get_all_documents()

            if not self._docs:
                self._initialized = True
                return

            tokenized_corpus = [self._tokenize(d["content"]) for d in self._docs]
            self._bm25 = BM25Okapi(tokenized_corpus)
            self._initialized = True

        except Exception:
            self._initialized = True

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple tokenization: whitespace split + Chinese character fallback."""
        tokens = text.split()
        # For Chinese text, also add individual characters as tokens
        # (rank-bm25 doesn't have a Chinese tokenizer built-in)
        char_tokens = [c for c in text if '\u4e00' <= c <= '\u9fff']
        return tokens + char_tokens

    def retrieve(self, query: str, top_k: int = 20) -> list[dict]:
        """Retrieve top-k documents matching the query via BM25."""
        self._initialize()

        if not self._bm25 or not self._docs:
            return []

        tokenized_query = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Sort by score descending
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]

        results: list[dict] = []
        for idx in ranked_indices:
            if scores[idx] <= 0:
                continue
            d = dict(self._docs[idx])
            d["score"] = float(scores[idx])
            results.append(d)

        return results

    def refresh(self) -> None:
        """Force reload of documents from Chroma."""
        self._initialized = False
        self._bm25 = None
        self._docs = []
