"""Checkpointer initialisation for LangGraph.

Uses AsyncSqliteSaver for persistent session storage.
The SQLite file lives in data/checkpoints.sqlite and survives restarts.
"""
from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver


_project_root = Path(__file__).resolve().parent.parent.parent
_db_dir = _project_root / "data"
_db_dir.mkdir(exist_ok=True)
_sqlite_path = _db_dir / "checkpoints.sqlite"

_saver: BaseCheckpointSaver | None = None
_saver_cm = None


def get_checkpointer() -> BaseCheckpointSaver:
    global _saver
    if _saver is not None:
        return _saver
    _saver = MemorySaver()
    return _saver


async def init_checkpointer() -> None:
    """Initialize the persistent SQLite checkpointer.

    Must be called during the FastAPI lifespan startup phase.
    Stores both the saver instance and the async context manager
    so the connection stays alive for the app's lifetime.
    """
    global _saver, _saver_cm

    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        _saver_cm = AsyncSqliteSaver.from_conn_string(str(_sqlite_path))
        _saver = await _saver_cm.__aenter__()
        await _saver.setup()
        print(f"[checkpointer] AsyncSqliteSaver connected → {_sqlite_path}")
        return
    except Exception as e:
        print(f"[checkpointer] AsyncSqliteSaver failed: {e}")

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        cm = SqliteSaver.from_conn_string(str(_sqlite_path))
        _saver = cm.__enter__()
        if hasattr(_saver, "setup"):
            _saver.setup()
        print(f"[checkpointer] Sync SqliteSaver connected → {_sqlite_path}")
        return
    except Exception as e:
        print(f"[checkpointer] Sync SqliteSaver failed: {e}")

    _saver = MemorySaver()
    print("[checkpointer] Fallback to MemorySaver (NOT persistent)")


async def close_checkpointer() -> None:
    """Gracefully close the checkpointer connection."""
    global _saver_cm
    if _saver_cm is not None:
        try:
            await _saver_cm.__aexit__(None, None, None)
            print("[checkpointer] AsyncSqliteSaver closed")
        except Exception:
            pass
        _saver_cm = None
