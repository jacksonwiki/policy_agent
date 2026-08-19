"""Final answer generation node — LLM produces the user-facing response."""
from __future__ import annotations

import logging
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..state import AgentState
from ...llm import get_llm, TaskType

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业、热情的保险智能助手。请根据提供的参考信息（对话历史+知识库+业务数据）回答用户的问题。

要求：
1. 回答要准确、简洁，符合保险行业规范
2. 如果参考信息中有数据，请引用具体数据
3. 如果参考信息不足，请明确告知用户"根据现有信息无法回答"，不要编造
4. 适当使用保险术语，但要通俗易懂
5. 回答用中文
6. 注意参考【对话历史】中的上下文，保持对话连贯性"""


def generate_final_answer(state: AgentState) -> dict:
    """Generate the final user-facing answer using the heavy LLM."""
    t0 = time.monotonic()
    user_query = state.get("user_query", "")
    assembled = state.get("assembled_context", "")
    intent = state.get("intent", "chitchat")
    compressed_history = state.get("compressed_history", "")

    llm = get_llm(TaskType.HEAVY)

    if intent == "chitchat":
        messages = []
        if compressed_history:
            messages.append(SystemMessage(content=f"对话历史：\n{compressed_history}"))
        messages.append(SystemMessage(content="你是一个友好的保险智能助手。请用中文自然地回应用户的问候或闲聊。"))
        messages.append(HumanMessage(content=user_query))
        response = llm.invoke(messages)
    else:
        prompt = f"""用户问题：{user_query}

参考信息：
{assembled}

请给出你的回答："""

        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])

    answer = response.content
    new_messages = list(state.get("messages", [])) + [
        {"type": "ai", "content": answer}
    ]

    logger.info(f"[latency] generate_final_answer cost={time.monotonic()-t0:.2f}s")
    return {"final_answer": answer, "messages": new_messages}