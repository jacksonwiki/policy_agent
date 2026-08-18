"""LangGraph Studio entry point.

Studio 要求一个无参数的可调用对象，返回编译后的 CompiledStateGraph。
使用 SQLite 持久化检查点，数据存储在 data/checkpoints.sqlite。
"""
from __future__ import annotations

from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from .core.graph import build_agent_graph


def _make_checkpointer():
    project_root = Path(__file__).resolve().parent.parent  # policy_agent root
    db_dir = project_root / "data"
    db_dir.mkdir(exist_ok=True)
    sqlite_path = db_dir / "checkpoints.sqlite"

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        cm = SqliteSaver.from_conn_string(str(sqlite_path))
        saver = cm.__enter__()
        saver.setup()
        print(f"[studio] SqliteSaver connected → {sqlite_path}")
        return saver
    except Exception as e:
        print(f"[studio] SqliteSaver failed: {e}, falling back to MemorySaver")
        return MemorySaver()


def agent():
    checkpointer = _make_checkpointer()
    graph = build_agent_graph(checkpointer=checkpointer)
    return graph.compile(checkpointer=checkpointer)