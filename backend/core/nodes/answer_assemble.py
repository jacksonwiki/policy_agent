"""Answer assembly node — merge RAG context + tool results into a unified prompt."""
from __future__ import annotations

from ..state import AgentState


def assemble_answer(state: AgentState) -> dict:
    """Merge compressed_history + rag_context + tool_results into a unified prompt."""
    compressed_history = state.get("compressed_history", "")
    rag_context = state.get("rag_context", "")
    tool_results = state.get("tool_results", [])

    parts: list[str] = []

    if compressed_history:
        parts.append("【对话历史】")
        parts.append(compressed_history)

    if rag_context:
        parts.append("【知识库参考】")
        parts.append(rag_context)

    if tool_results:
        parts.append("【业务数据】")
        for tr in tool_results:
            if isinstance(tr, dict):
                if tr.get("error"):
                    parts.append(f"- 工具 {tr.get('name', '?')} 执行失败: {tr.get('error')}")
                else:
                    parts.append(f"- 工具 {tr.get('name', '?')} 返回: {tr.get('result', '')}")
            else:
                if getattr(tr, "error", None):
                    parts.append(f"- 工具 {tr.name} 执行失败: {tr.error}")
                else:
                    parts.append(f"- 工具 {tr.name} 返回: {tr.result}")

    assembled = "\n\n".join(parts) if parts else "(无参考信息)"

    return {"assembled_context": assembled}