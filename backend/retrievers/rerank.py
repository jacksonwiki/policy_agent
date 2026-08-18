"""Reranker using Ollama bge-reranker-v2-m3 embedding model for relevance scoring."""
from __future__ import annotations

import math

import httpx

from ..config import get_settings


class Reranker:
    """Cross-encoder style reranker via Ollama embedding model, with heuristic fallback."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model_available: bool | None = None

    @property
    def model_available(self) -> bool:
        if self._model_available is not None:
            return self._model_available
        try:
            resp = httpx.Client(timeout=5.0).get(
                f"{self._settings.ollama_base_url}/api/tags"
            )
            if resp.status_code != 200:
                self._model_available = False
                return False
            tags = resp.json().get("models", [])
            model_name = self._settings.rerank_model
            self._model_available = any(
                m.get("name", "").startswith(model_name) for m in tags
            )
        except Exception:
            self._model_available = False
        return self._model_available

    def rerank(
        self,
        query: str,
        documents: list[dict],
        top_k: int | None = None,
    ) -> list[dict]:
        if not documents:
            return []

        k = top_k or self._settings.rerank_max_top_k

        if self.model_available:
            try:
                return self._embed_rerank(query, documents, k)
            except Exception:
                pass

        return self._heuristic_rerank(query, documents, k)

    def _embed_rerank(
        self, query: str, documents: list[dict], k: int
    ) -> list[dict]:
        """Use Ollama bge-reranker-v2-m3 to embed query+doc pairs and compute relevance.

        The model produces embeddings that encode the semantic relevance between
        the query and each document. We embed "query [SEP] document" for each pair
        and use the embedding norm as a relevance signal.
        """
        client = httpx.Client(timeout=30.0)
        model = self._settings.rerank_model
        base_url = self._settings.ollama_base_url

        # Build query-document pairs for cross-encoder style scoring
        scored_docs: list[dict] = []
        for doc in documents:
            content = doc.get("content", "")
            # Cross-encoder input: query + separator + document
            pair_text = f"{query}\n{content}"

            resp = client.post(
                f"{base_url}/api/embed",
                json={"model": model, "input": pair_text},
            )
            resp.raise_for_status()
            data = resp.json()
            embedding = data.get("embeddings", [[]])[0]

            # Use embedding magnitude as relevance score
            score = math.sqrt(sum(x * x for x in embedding)) if embedding else 0.0
            d = dict(doc)
            d["rerank_score"] = score
            scored_docs.append(d)

        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_docs[:k]

    def _heuristic_rerank(
        self, query: str, documents: list[dict], k: int
    ) -> list[dict]:
        """Simple heuristic rerank using keyword overlap and existing scores."""
        query_lower = query.lower()
        query_chars = set(query_lower)

        scored_docs: list[dict] = []
        for doc in documents:
            d = dict(doc)
            content_lower = doc.get("content", "").lower()
            content_chars = set(content_lower)

            char_overlap = len(query_chars & content_chars) / max(
                len(query_chars), 1
            )

            existing_score = doc.get("score", 0)
            combined_score = existing_score * 0.6 + char_overlap * 0.4

            d["rerank_score"] = combined_score
            scored_docs.append(d)

        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_docs[:k]
