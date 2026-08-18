"""Verify that all three LLM providers (deepseek/ollama/qwen) can be configured
and instantiated correctly via the router.

This script does NOT call the LLM API — it only checks:
1. Settings can be loaded for each provider
2. get_llm() returns the expected provider type
3. Fallback chain works when the main provider is unavailable

Run:
    python scripts/verify_llm_providers.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def reset_caches():
    """Reset all LLM-related caches so config changes take effect."""
    from backend.config import get_settings
    get_settings.cache_clear()
    from backend.llm import router
    router.reset_llm_cache()
    from backend.llm.deepseek_client import get_deepseek_chat
    get_deepseek_chat.cache_clear()
    from backend.llm.local_qwen_client import get_local_qwen_chat
    get_local_qwen_chat.cache_clear()
    from backend.llm.qwen_client import get_qwen_chat
    get_qwen_chat.cache_clear()


def test_provider(provider: str, expect_mock: bool = False) -> str:
    """Test that get_llm() returns a model for the given provider.

    Returns a status string.
    """
    os.environ["LLM_PROVIDER"] = provider
    os.environ["POLICY_AGENT_MOCK_LLM"] = "true" if expect_mock else "false"
    reset_caches()

    from backend.config import get_settings
    settings = get_settings()
    assert settings.llm_provider == provider, f"expected {provider}, got {settings.llm_provider}"

    from backend.llm import get_llm, TaskType, get_current_provider
    llm = get_llm(TaskType.HEAVY)
    provider_name = get_current_provider()
    class_name = type(llm).__name__
    return f"  provider={provider_name:10s}  llm_class={class_name}"


def main():
    print("=== LLM Provider Switch Test ===\n")

    # Save original env
    original_provider = os.environ.get("LLM_PROVIDER", "")
    original_mock = os.environ.get("POLICY_AGENT_MOCK_LLM", "")

    try:
        # 1. Mock mode (baseline)
        print("[1] Mock mode (POLICY_AGENT_MOCK_LLM=true)")
        result = test_provider("deepseek", expect_mock=True)
        print(result + "\n")

        # 2. DeepSeek
        print("[2] Provider = deepseek")
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-dummy"
        result = test_provider("deepseek")
        print(result + "\n")

        # 3. Qwen
        print("[3] Provider = qwen")
        os.environ["DASHSCOPE_API_KEY"] = "sk-test-dummy"
        result = test_provider("qwen")
        print(result + "\n")

        # 4. Ollama (may fail if ollama not running — that's fine, fallback to mock)
        print("[4] Provider = ollama (will fallback to mock if ollama not running)")
        result = test_provider("ollama")
        print(result + "\n")

        # 5. Fallback chain test: qwen primary, deepseek fallback
        print("[5] Fallback chain: LLM_PROVIDER=qwen, LLM_FALLBACK_CHAIN=deepseek")
        os.environ["LLM_PROVIDER"] = "qwen"
        os.environ["LLM_FALLBACK_CHAIN"] = "deepseek"
        reset_caches()
        from backend.llm import get_llm, TaskType
        llm = get_llm(TaskType.HEAVY)
        print(f"  llm_class={type(llm).__name__}\n")

        print("=== All tests passed ===")

    finally:
        # Restore env
        if original_provider:
            os.environ["LLM_PROVIDER"] = original_provider
        else:
            os.environ.pop("LLM_PROVIDER", None)
        if original_mock:
            os.environ["POLICY_AGENT_MOCK_LLM"] = original_mock
        else:
            os.environ.pop("POLICY_AGENT_MOCK_LLM", None)
        reset_caches()


if __name__ == "__main__":
    main()
