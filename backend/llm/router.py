"""Dual-LLM router: DeepSeek for heavy tasks, local Ollama for light tasks.

Supports mock mode for testing without real LLM services.
Set POLICY_AGENT_MOCK_LLM=true to force mock mode.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from .deepseek_client import get_deepseek_chat
from .local_qwen_client import get_local_qwen_chat


def _make_mock_llm(template: str = "Mock response") -> BaseChatModel:
    """Create a mock LLM that returns predictable responses for testing."""
    responses = [template for _ in range(100)]
    return FakeListChatModel(responses=responses)


class TaskType(str, Enum):
    HEAVY = "heavy"
    LIGHT = "light"


_llm_cache: dict[str, BaseChatModel] = {}


def _is_mock_mode() -> bool:
    """Check if mock mode is enabled via environment variable."""
    return os.environ.get("POLICY_AGENT_MOCK_LLM", "false").lower() in ("true", "1", "yes")


def get_llm(task_type: TaskType | Literal["heavy", "light"]) -> BaseChatModel:
    """Return the appropriate LLM instance for the given task type.

    In mock mode, always returns mock LLMs.
    Otherwise, tries real LLM first, falls back to mock on failure.
    """
    t = TaskType(task_type) if isinstance(task_type, str) else task_type
    cache_key = t.value

    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    if _is_mock_mode():
        llm = _make_mock_llm(f"[{t.value}] mock response")
    else:
        # 优先使用 DeepSeek，不可用时降级到本地 Ollama
        try:
            llm = get_deepseek_chat()
        except Exception:
            try:
                llm = get_local_qwen_chat()
            except Exception:
                llm = _make_mock_llm(f"[{t.value}] fallback mock")

    _llm_cache[cache_key] = llm
    return llm


def reset_llm_cache() -> None:
    """Clear the LLM cache (useful after config changes)."""
    _llm_cache.clear()
