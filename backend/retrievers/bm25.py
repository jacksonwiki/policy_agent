"""BM25 keyword retriever — uses rank-bm25 for in-memory BM25 scoring."""
from __future__ import annotations

from typing import Any

from ..config import get_settings


class BM25Retriever:
    """In-memory BM25 retriever.

    Documents are loaded from VectorRetriever on first init and cached at class level
    so that all instances share the same index.
    """

    _shared_bm25: Any = None
    _shared_docs: list[dict] = []
    _initialized: bool = False

    def __init__(self) -> None:
        pass

    def _initialize(self) -> None:
        """Load all docs from VectorRetriever and build BM25 index (once)."""
        if BM25Retriever._initialized:
            return

        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            raise RuntimeError("rank-bm25 is not installed. Run: pip install rank-bm25")

        try:
            from .vector import VectorRetriever
            vr = VectorRetriever()
            BM25Retriever._shared_docs = vr.get_all_documents()

            if not BM25Retriever._shared_docs:
                BM25Retriever._initialized = True
                return

            tokenized_corpus = [self._tokenize(d["content"]) for d in BM25Retriever._shared_docs]
            BM25Retriever._shared_bm25 = BM25Okapi(tokenized_corpus)
            BM25Retriever._initialized = True

        except Exception:
            BM25Retriever._initialized = True

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

        if not BM25Retriever._shared_bm25 or not BM25Retriever._shared_docs:
            return []

        tokenized_query = self._tokenize(query)
        scores = BM25Retriever._shared_bm25.get_scores(tokenized_query)

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
            d = dict(BM25Retriever._shared_docs[idx])
            d["score"] = float(scores[idx])
            results.append(d)

        return results

    def refresh(self) -> None:
        """Force reload of documents from VectorRetriever."""
        BM25Retriever._initialized = False
        BM25Retriever._shared_bm25 = None
        BM25Retriever._shared_docs = []