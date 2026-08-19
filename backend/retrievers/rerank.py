"""Reranker using Ollama bge-reranker-v2-m3 embedding model for relevance scoring."""
from __future__ import annotations

import logging
import math
import time

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


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
        t0 = time.monotonic()
        if not documents:
            return []

        k = top_k or self._settings.rerank_max_top_k

        if self.model_available:
            try:
                result = self._embed_rerank(query, documents, k)
                logger.info(f"[latency] rerank(embed) cost={time.monotonic()-t0:.2f}s")
                return result
            except Exception:
                logger.info(f"[latency] rerank(embed-fail) cost={time.monotonic()-t0:.2f}s")
                pass

        result = self._heuristic_rerank(query, documents, k)
        logger.info(f"[latency] rerank(heuristic) cost={time.monotonic()-t0:.2f}s")
        return result

    def _embed_rerank(
        self, query: str, documents: list[dict], k: int
    ) -> list[dict]:
        """Rerank via embedding cosine similarity fused with the RRF prior.

        The embedding norm of a query-doc pair carries no relevance signal, so we
        compute the cosine similarity between the query embedding and each document
        embedding (semantic relevance), then blend it with the normalized RRF score
        so the keyword/vector fusion prior is not discarded.
        """
        client = httpx.Client(timeout=60.0)
        model = self._settings.rerank_model
        base_url = self._settings.ollama_base_url

        def _embed_batch(texts: list[str]) -> list[list[float]]:
            # Ollama /api/embed 支持 input 传字符串数组，一次 HTTP 调用返回全部向量，
            # 避免逐个文档串行请求（最多可省 19 次往返）。
            resp = client.post(
                f"{base_url}/api/embed",
                json={"model": model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("embeddings", []) or []

        try:
            query_embs = _embed_batch([query])
            query_emb = query_embs[0] if query_embs else []
        except Exception:
            return self._heuristic_rerank(query, documents, k)
        if not query_emb:
            return self._heuristic_rerank(query, documents, k)

        contents = [doc.get("content", "") for doc in documents]
        try:
            doc_embs = _embed_batch(contents)
        except Exception:
            # 批量失败时逐条兜底，避免整批结果丢失
            doc_embs = []
            for c in contents:
                try:
                    doc_embs.append(_embed_batch([c])[0])
                except Exception:
                    doc_embs.append([])

        scored_docs: list[dict] = []
        for doc, doc_emb in zip(documents, doc_embs):
            if not doc_emb:
                continue

            cosine = self._cosine_similarity(query_emb, doc_emb)
            # 融合 RRF 先验（归一化），避免语义相近但关键词不匹配的噪声文档反超。
            # 只取 rrf_score：原始 vector/bm25 分数量纲不可比，混用会主导排序。
            prior = doc.get("rrf_score", 0) or 0.0
            prior_norm = min(1.0, prior * 20.0)

            d = dict(doc)
            d["rerank_score"] = cosine * 0.7 + prior_norm * 0.3
            scored_docs.append(d)

        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_docs[:k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

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

            existing_score = doc.get("rrf_score", 0) or 0.0
            combined_score = existing_score * 0.6 + char_overlap * 0.4

            d["rerank_score"] = combined_score
            scored_docs.append(d)

        scored_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_docs[:k]
