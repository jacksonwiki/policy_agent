"""LLM router — supports DeepSeek / Ollama / Qwen with configurable switching.

Configuration (via .env):
- LLM_PROVIDER: main provider, one of `deepseek` | `ollama` | `qwen` (default: deepseek)
- LLM_FALLBACK_CHAIN: comma-separated fallback order, e.g. "ollama,qwen"
  (empty = no fallback, mock LLM used as last resort)

Set POLICY_AGENT_MOCK_LLM=true to force mock mode for offline testing.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Callable, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from ..config import get_settings
from .deepseek_client import get_deepseek_chat
from .local_qwen_client import get_local_qwen_chat
from .qwen_client import get_qwen_chat


def _make_mock_llm(template: str = "Mock response") -> BaseChatModel:
    """Create a mock LLM that returns predictable responses for testing."""
    responses = [template for _ in range(100)]
    return FakeListChatModel(responses=responses)


class TaskType(str, Enum):
    HEAVY = "heavy"
    LIGHT = "light"


# Provider name → factory callable
_PROVIDER_FACTORIES: dict[str, Callable[[], BaseChatModel]] = {
    "deepseek": get_deepseek_chat,
    "ollama": get_local_qwen_chat,
    "qwen": get_qwen_chat,
}

_llm_cache: dict[str, BaseChatModel] = {}


def _is_mock_mode() -> bool:
    """Check if mock mode is enabled via environment variable."""
    return os.environ.get("POLICY_AGENT_MOCK_LLM", "false").lower() in ("true", "1", "yes")


def _build_fallback_chain(provider: str) -> list[str]:
    """Build the provider attempt order: [provider] + fallback_chain (deduped)."""
    settings = get_settings()
    chain = [provider]
    for item in settings.llm_fallback_chain.split(","):
        item = item.strip().lower()
        if item and item not in chain:
            chain.append(item)
    return chain


def get_llm(task_type: TaskType | Literal["heavy", "light"] = TaskType.HEAVY) -> BaseChatModel:
    """Return the appropriate LLM instance for the given task type.

    Resolution order:
    1. Mock mode → return mock LLM immediately
    2. Try configured LLM_PROVIDER first
    3. On failure, try each provider in LLM_FALLBACK_CHAIN
    4. If all fail, return a mock LLM as last resort

    The instance is cached per task_type.
    """
    t = TaskType(task_type) if isinstance(task_type, str) else task_type
    cache_key = t.value

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if _is_mock_mode():
        llm = _make_mock_llm(f"[{t.value}] mock response")
        _llm_cache[cache_key] = llm
        return llm

    settings = get_settings()
    chain = _build_fallback_chain(settings.llm_provider)

    llm: BaseChatModel | None = None
    last_error: Exception | None = None
    for provider in chain:
        factory = _PROVIDER_FACTORIES.get(provider)
        if factory is None:
            continue
        try:
            llm = factory()
            break
        except Exception as e:
            last_error = e
            continue

    if llm is None:
        llm = _make_mock_llm(f"[{t.value}] fallback mock (last_error={last_error})")

    _llm_cache[cache_key] = llm
    return llm


def reset_llm_cache() -> None:
    """Clear the LLM cache (useful after config changes)."""
    _llm_cache.clear()


def get_current_provider() -> str:
    """Return the effective provider name (for debugging / health checks)."""
    if _is_mock_mode():
        return "mock"
    settings = get_settings()
    return settings.llm_provider
