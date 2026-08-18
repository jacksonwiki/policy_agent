"""Qwen / DashScope chat model client.

Uses DashScope's OpenAI-compatible API endpoint so we can reuse
langchain_openai.ChatOpenAI without any extra SDK dependency.

Set DASHSCOPE_API_KEY in .env to enable.
Common models: qwen-plus, qwen-turbo, qwen-max, qwen-long.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models.chat_models import BaseChatModel

from ..config import get_settings


@lru_cache
def get_qwen_chat() -> BaseChatModel:
    """Lazy / cached factory for Qwen (DashScope OpenAI-compatible mode).

    Raises RuntimeError if DASHSCOPE_API_KEY is not configured.
    """
    settings = get_settings()
    if not settings.qwen_api_key:
        raise RuntimeError(
            "DASHSCOPE_API_KEY is not configured. "
            "Set it in .env (env var: DASHSCOPE_API_KEY) to use Qwen."
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        try:
            from langchain_community.chat_models import ChatOpenAI
        except ImportError as e:
            raise RuntimeError(
                "ChatOpenAI is not available. "
                "Install langchain-openai: pip install langchain-openai"
            ) from e

    return ChatOpenAI(
        api_key=settings.qwen_api_key,
        base_url=settings.qwen_base_url,
        model=settings.qwen_model,
        temperature=settings.qwen_temperature,
        max_tokens=settings.qwen_max_tokens,
    )
