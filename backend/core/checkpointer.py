"""Checkpointer initialisation for LangGraph.

Uses SqliteSaver for persistent session storage.
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


def _build_sqlite_saver() -> BaseCheckpointSaver | None:
    """Try to create a SQLite saver (sync). Returns None if unavailable."""
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        cm = SqliteSaver.from_conn_string(str(_sqlite_path))
        saver = cm.__enter__()
        saver.setup()
        print(f"[checkpointer] SqliteSaver connected → {_sqlite_path}")
        return saver
    except Exception as e:
        print(f"[checkpointer] SqliteSaver failed: {e}")
        return None


def get_checkpointer() -> BaseCheckpointSaver:
    """Return the persistent checkpointer.

    Uses SqliteSaver (sync) by default; falls back to MemorySaver if SQLite
    is not available.  The same instance is reused across calls.
    """
    global _saver
    if _saver is not None:
        return _saver

    saver = _build_sqlite_saver()
    if saver is not None:
        _saver = saver
        return _saver

    _saver = MemorySaver()
    print("[checkpointer] Falling back to MemorySaver (NOT persistent)")
    return _saver


async def init_checkpointer() -> None:
    """Initialize the persistent SQLite checkpointer.

    Must be called during the FastAPI lifespan startup phase.
    Prefers async SqliteSaver; falls back to sync; then to MemorySaver.
    """
    global _saver, _saver_cm

    # 1. Try async SQLite
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        _saver_cm = AsyncSqliteSaver.from_conn_string(str(_sqlite_path))
        _saver = await _saver_cm.__aenter__()
        await _saver.setup()
        print(f"[checkpointer] AsyncSqliteSaver connected → {_sqlite_path}")
        return
    except Exception as e:
        print(f"[checkpointer] AsyncSqliteSaver failed: {e}")

    # 2. Try sync SQLite
    saver = _build_sqlite_saver()
    if saver is not None:
        _saver = saver
        return

    # 3. Fallback
    _saver = MemorySaver()
    print("[checkpointer] Falling back to MemorySaver (NOT persistent)")


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