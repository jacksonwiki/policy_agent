"""Application settings loaded from environment variables / .env."""
from __future__ import annotations

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

    # ── DeepSeek LLM (主力) ──────────────────────────────
    deepseek_api_key: str = Field(default="", json_schema_extra={"env": "DEEPSEEK_API_KEY"})
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_temperature: float = 0.3
    deepseek_max_tokens: int = 4096

    # ── 本地 Ollama (辅助) ───────────────────────────────
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.5:0.8b"
    ollama_embedding_model: str = "nomic-embed-text:latest"
    ollama_temperature: float = 0.3

    # ── Rerank ────────────────────────────────────────────
    rerank_model: str = "dengcao/bge-reranker-v2-m3"
    rerank_max_top_k: int = 5

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
    rag_top_k_retrieval: int = 20
    rag_top_k_rrf: int = 20
    rag_rrf_k: int = 60
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 100
    rag_max_context_tokens: int = 3000

    # ── Agent 参数 ────────────────────────────────────────
    agent_max_tool_rounds: int = 5
    agent_max_sub_queries: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
