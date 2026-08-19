"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import configure_langsmith, get_settings
from .api.auth import UserStore
from .api.routes import router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup/shutdown hooks."""
    settings = get_settings()

    # Initialize default admin user
    UserStore.init_default_admin()

    # Initialize persistent checkpointer (SQLite / Postgres / Memory fallback)
    from .core.checkpointer import init_checkpointer, close_checkpointer
    await init_checkpointer()

    yield

    # Cleanup
    await close_checkpointer()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    # 必须先于任何 LangGraph / LLM 调用注入 LangSmith 环境变量
    configure_langsmith()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # restrict in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routes
    app.include_router(router, prefix="/api")

    @app.get("/health")
    async def health_check():
        from .llm.router import get_current_provider
        return {
            "status": "ok",
            "app": settings.app_name,
            "llm_provider": get_current_provider(),
        }

    return app


app = create_app()
