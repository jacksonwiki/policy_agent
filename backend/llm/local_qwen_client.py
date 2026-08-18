"""Local Ollama chat model client."""
from __future__ import annotations

from functools import lru_cache

import httpx
from langchain_core.language_models.chat_models import BaseChatModel

from ..config import get_settings


@lru_cache
def get_local_qwen_chat() -> BaseChatModel:
    """Lazy / cached factory for Ollama-hosted qwen3.5:0.8b.

    Raises RuntimeError if Ollama is not reachable.
    """
    settings = get_settings()

    # Quick health check
    try:
        client = httpx.Client(timeout=2.0)
        resp = client.get(f"{settings.ollama_base_url}/api/tags")
        resp.raise_for_status()
    except Exception as e:
        raise RuntimeError(
            f"Ollama is not reachable at {settings.ollama_base_url}: {e}"
        )

    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        try:
            from langchain_community.chat_models import ChatOllama
        except ImportError:
            raise RuntimeError(
                "ChatOllama is not available. "
                "Install langchain-ollama: pip install langchain-ollama"
            )

    return ChatOllama(
        model=settings.ollama_model,
        base_url=settings.ollama_base_url,
        temperature=settings.ollama_temperature,
    )
