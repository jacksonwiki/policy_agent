"""DeepSeek chat model client (Lightweight wrapper over langchain_deepseek)."""
from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from ..config import get_settings


@lru_cache
def get_deepseek_chat() -> BaseChatModel:
    """Lazy / cached factory so the LLM is only instantiated when first called."""
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY is not configured. Set it in .env or environment variable."
        )

    try:
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            temperature=settings.deepseek_temperature,
            max_tokens=settings.deepseek_max_tokens,
        )
    except ImportError:
        pass

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        from langchain_community.chat_models import ChatOpenAI

    return ChatOpenAI(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_tokens,
    )