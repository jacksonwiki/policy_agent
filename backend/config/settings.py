"""Application settings loaded from environment variables / .env."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── 服务 ──────────────────────────────────────────────
    app_name: str = "PolicyAgent"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = True

    # ── LLM Provider 切换 ───────────────────────────────
    # 可选: deepseek | ollama | qwen   默认 deepseek
    llm_provider: Literal["deepseek", "ollama", "qwen"] = Field(
        default="deepseek", json_schema_extra={"env": "LLM_PROVIDER"}
    )
    # 主 LLM 不可用时的降级顺序，逗号分隔，空值表示不降级
    # 示例: "ollama,qwen" 表示主 LLM 失败后依次尝试 ollama → qwen → mock
    llm_fallback_chain: str = Field(
        default="ollama,qwen", json_schema_extra={"env": "LLM_FALLBACK_CHAIN"}
    )

    # ── DeepSeek LLM ──────────────────────────────────────
    deepseek_api_key: str = Field(default="", json_schema_extra={"env": "DEEPSEEK_API_KEY"})
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_temperature: float = 0.3
    deepseek_max_tokens: int = 4096
    deepseek_timeout: int = 30
    deepseek_max_retries: int = 1

    # ── 本地 Ollama ───────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:0.8b"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_temperature: float = 0.3

    # ── 千问 (Qwen / DashScope) ──────────────────────────
    # 通过 DashScope OpenAI 兼容接口调用
    qwen_api_key: str = Field(default="", json_schema_extra={"env": "DASHSCOPE_API_KEY"})
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_temperature: float = 0.3
    qwen_max_tokens: int = 4096

    # ── Rerank ────────────────────────────────────────────
    # 重排序开关：默认关闭，开启后会在 RRF 融合结果上再跑一遍 rerank 模型精排
    rerank_enabled: bool = Field(
        default=False, json_schema_extra={"env": "RERANK_ENABLED"}
    )
    rerank_model: str = "dengcao/bge-reranker-v2-m3"
    rerank_max_top_k: int = 5

    # ── LangSmith 可观测性（可选）──────────────────────────
    # 填好 LANGCHAIN_API_KEY 并把 LANGCHAIN_TRACING_V2 置为 true 后，
    # LangGraph / LLM 调用会自动上报 trace 到 LangSmith，用于调试。
    # 参考: https://smith.langchain.com → Settings → API Keys
    langchain_tracing_v2: bool = Field(
        default=False, json_schema_extra={"env": "LANGCHAIN_TRACING_V2"}
    )
    langchain_api_key: str = Field(
        default="", json_schema_extra={"env": "LANGCHAIN_API_KEY"}
    )
    langchain_project: str = Field(
        default="policy_agent", json_schema_extra={"env": "LANGCHAIN_PROJECT"}
    )
    langchain_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        json_schema_extra={"env": "LANGCHAIN_ENDPOINT"},
    )

    # ── 向量库 Chroma ────────────────────────────────────
    chroma_collection: str = "policy_knowledge"
    embedding_dim: int = 768  # nomic-embed-text 输出维度

    # ── JWT / 鉴权 ───────────────────────────────────────
    jwt_secret: str = "change-me-in-production-please"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h

    # ── 默认管理员 ────────────────────────────────────────
    default_admin_username: str = "admin"
    default_admin_password: str = "admin"

    # ── HITL ──────────────────────────────────────────────
    hitl_timeout_minutes: int = 30

    # ── RAG 参数 ──────────────────────────────────────────
    rag_top_k_retrieval: int = 15
    rag_top_k_rrf: int = 12
    rag_rrf_k: int = 60
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 100
    rag_max_context_tokens: int = 3000

    # ── Agent 参数 ────────────────────────────────────────
    agent_max_tool_rounds: int = 5
    agent_max_sub_queries: int = 5

    # ── 短期记忆 / 压缩 ──────────────────────────────────
    memory_max_recent_messages: int = 6
    memory_summary_max_tokens: int = 500
    memory_compress_threshold: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_langsmith() -> None:
    """Export LangSmith settings into os.environ so that langchain-core's
    auto-instrumentation (langsmith SDK) picks them up at runtime.

    NOTE: pydantic-settings only reads declared fields from .env and does NOT
    write them back into os.environ, so without this injection the
    LANGCHAIN_* vars in .env would never be seen by the langsmith SDK.
    """
    settings = get_settings()
    if not settings.langchain_api_key:
        # 没有配置 key 时强制关闭 tracing，避免误开
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        os.environ["LANGSMITH_TRACING"] = "false"
        return

    tracing = "true" if settings.langchain_tracing_v2 else "false"
    # 两个前缀都设置，兼容 langsmith SDK 不同版本
    os.environ["LANGCHAIN_TRACING_V2"] = tracing
    os.environ["LANGSMITH_TRACING"] = tracing
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint