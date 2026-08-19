"""Conversation compression node — sliding window + pre-summary.

Strategy:
1. Keep the most recent N messages intact (sliding window).
2. Summarize older messages into a running "conversation_summary" using the
   currently active LLM (same model used for generation).
3. On each pass, merge the old summary + newly evicted messages into a new
   summary, so context is preserved across turns.
"""
from __future__ import annotations

import logging
import time
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from ..state import AgentState
from ...config import get_settings
from ...llm import get_llm, TaskType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个对话历史摘要助手。请将以下对话历史压缩为简洁的中文摘要，保留：
1. 用户的核心需求和意图
2. 已确认的关键事实、数据、保单号等
3. 未解决的问题
4. 双方达成的结论或共识

要求：
- 用简洁的中文输出
- 不超过规定字数
- 保留关键实体名称和数字
"""

SUMMARY_MERGE_PROMPT = """以下是之前的对话摘要和新增的对话内容，请将它们合并为一个更新的摘要。

之前的摘要：
{existing_summary}

新增对话：
{newer_transcript}

请合并为一个完整的摘要，保留所有关键信息。"""


def _msg_to_text(msg: BaseMessage | dict) -> str:
    if isinstance(msg, dict):
        msg_type = msg.get("type", "")
        content = msg.get("content", "")
    else:
        msg_type = getattr(msg, "type", "")
        content = getattr(msg, "content", "")

    if msg_type in ("human", "user"):
        return f"用户: {content}"
    elif msg_type in ("ai", "assistant"):
        return f"助手: {content}"
    return ""


def _build_transcript(messages: list[BaseMessage | dict]) -> str:
    parts = []
    for m in messages:
        t = _msg_to_text(m)
        if t:
            parts.append(t)
    return "\n".join(parts)


def compress_conversation(state: AgentState) -> dict:
    """Compress conversation via sliding window + pre-summary.

    Returns:
        compressed_history: str  — the full context to feed downstream
                                   (summary + recent window).
        conversation_summary: str — the updated rolling summary.
    """
    t0 = time.monotonic()
    settings = get_settings()
    messages = state.get("messages", [])
    existing_summary = state.get("conversation_summary", "")
    max_recent = settings.memory_max_recent_messages
    threshold = settings.memory_compress_threshold

    if len(messages) <= threshold:
        transcript = _build_transcript(messages)
        return {
            "compressed_history": transcript,
            "conversation_summary": existing_summary,
        }

    split_idx = max(0, len(messages) - max_recent)
    older = messages[:split_idx]
    recent = messages[split_idx:]

    older_transcript = _build_transcript(older)
    recent_transcript = _build_transcript(recent)

    llm = get_llm(TaskType.LIGHT)

    if existing_summary:
        prompt = SUMMARY_MERGE_PROMPT.format(
            existing_summary=existing_summary,
            newer_transcript=older_transcript,
        )
    else:
        prompt = older_transcript

    try:
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        new_summary = response.content.strip()
    except Exception:
        new_summary = existing_summary
        if older_transcript:
            new_summary = f"{existing_summary}\n{older_transcript}".strip()

    parts = []
    if new_summary:
        parts.append(f"[历史摘要]\n{new_summary}")
    if recent_transcript:
        parts.append(f"[最近对话]\n{recent_transcript}")

    compressed_history = "\n\n".join(parts)

    logger.info(f"[latency] compress_conversation cost={time.monotonic()-t0:.2f}s")
    return {
        "compressed_history": compressed_history,
        "conversation_summary": new_summary,
    }