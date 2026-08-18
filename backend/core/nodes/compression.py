"""Conversation compression node — summarise long histories before routing."""
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..state import AgentState
from ...llm import get_llm, TaskType

SYSTEM_PROMPT = """你是一个对话历史压缩助手。请将以下对话历史压缩成简洁的摘要，保留：
1. 用户的核心需求和意图
2. 已确认的关键事实和数据
3. 未解决的问题

用中文输出，不超过200字。"""


def compress_conversation(state: AgentState) -> dict:
    """Compress long conversation history into a compact summary.

    For short histories (<=3 messages) we skip compression and return the raw text.
    """
    messages = state.get("messages", [])
    if len(messages) <= 3:
        return {"compressed_history": ""}

    llm = get_llm(TaskType.LIGHT)

    # Build a text transcript
    transcript_parts: list[str] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            transcript_parts.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage):
            transcript_parts.append(f"助手: {msg.content}")

    transcript = "\n".join(transcript_parts)

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=transcript),
    ])

    return {"compressed_history": response.content}
