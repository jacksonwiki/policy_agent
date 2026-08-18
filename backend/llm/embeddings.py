"""Embedding model client with Ollama and mock fallback."""
from __future__ import annotations

import os
import random
from functools import lru_cache

import httpx
from langchain_core.embeddings import Embeddings

from ..config import get_settings


class MockEmbeddings(Embeddings):
    """Simple mock embeddings for testing — produces deterministic pseudo-vectors."""

    def __init__(self, dim: int = 768):
        self._dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._text_to_vector(text)

    def _text_to_vector(self, text: str) -> list[float]:
        random.seed(hash(text))
        vector = [random.uniform(-1, 1) for _ in range(self._dim)]
        norm = sum(x * x for x in vector) ** 0.5
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector


@lru_cache
def get_embeddings() -> Embeddings:
    settings = get_settings()
    mock_mode = os.environ.get("POLICY_AGENT_MOCK_LLM", "false").lower() in ("true", "1", "yes")

    if mock_mode:
        return MockEmbeddings(dim=settings.embedding_dim)

    try:
        client = httpx.Client(timeout=2.0)
        resp = client.get(f"{settings.ollama_base_url}/api/tags")
        resp.raise_for_status()
    except Exception:
        return MockEmbeddings(dim=settings.embedding_dim)

    try:
        from langchain_ollama import OllamaEmbeddings
    except ImportError:
        from langchain_community.embeddings import OllamaEmbeddings

    return OllamaEmbeddings(
        model=settings.ollama_embedding_model,
        base_url=settings.ollama_base_url,
    )
