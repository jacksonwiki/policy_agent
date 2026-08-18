"""Intent router node — decide rag / tool / both / chitchat."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..state import AgentState
from ...llm import get_llm, TaskType

SYSTEM_PROMPT = """你是一个保险智能助手的意图路由器。请判断用户的问题需要：

- "rag": 只需要从知识库检索（比如保险条款、产品介绍、理赔流程等知识性问题）
- "tool": 只需要调用保险业务接口（比如查询保单、查询理赔进度、核保、支付等操作性问题）
- "both": 既需要知识库，又需要调用接口（比如"我的寿险保单有哪些保障"需要先查保单再查知识库中的保障条款）
- "chitchat": 闲聊或问候，无需检索也无需调用接口

判断规则：
1. 涉及"我的保单/理赔/缴费/状态/进度"等个人数据 → tool 或 both
2. 涉及"什么是/如何/条款/流程/介绍"等知识 → rag
3. 同时涉及个人数据和知识 → both
4. 问候/感谢/闲聊 → chitchat

输出JSON：{"intent": "rag|tool|both|chitchat", "reason": "判断理由", "tool_names": ["需要调用的工具名"]}"""


# Keyword-based fallback rules
TOOL_KEYWORDS = [
    "我的保单", "我的理赔", "我的缴费", "我的保险",
    "保单状态", "理赔进度", "缴费记录", "保单详情",
    "查询保单", "查询理赔", "查保单", "查理赔",
    "核保", "出单", "支付", "退保", "受益人",
    "我的", "帮我查", "帮我看",
]

RAG_KEYWORDS = [
    "什么是", "怎么", "如何", "条款", "流程", "介绍",
    "保障", "责任", "除外", "免赔", "犹豫期",
    "解释", "说明", "对比", "区别",
]


def _keyword_fallback(query: str) -> str | None:
    """Simple keyword-based fallback to prevent LLM misclassification."""
    has_tool = any(kw in query for kw in TOOL_KEYWORDS)
    has_rag = any(kw in query for kw in RAG_KEYWORDS)

    if has_tool and has_rag:
        return "both"
    if has_tool:
        return "tool"
    if has_rag:
        return "rag"
    return None  # let LLM decide


def route_intent(state: AgentState) -> dict:
    """Route user intent to rag / tool / both / chitchat."""
    user_query = state.get("user_query", "")
    rewritten = state.get("rewritten_query", user_query)

    # Keyword fallback first (most reliable)
    kw_result = _keyword_fallback(rewritten)

    # Also check original query for keywords
    kw_result_orig = _keyword_fallback(user_query)

    try:
        llm = get_llm(TaskType.HEAVY)
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"用户问题：{rewritten}"),
        ])

        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
            if raw.endswith("```"):
                raw = raw[:-3]

        try:
            parsed = json.loads(raw)
            intent = parsed.get("intent", "unknown")
        except json.JSONDecodeError:
            intent = "unknown"
    except Exception:
        intent = "unknown"

    # Merge: keyword result takes precedence
    final_intent = intent
    if kw_result:
        final_intent = kw_result
    elif kw_result_orig:
        final_intent = kw_result_orig

    if final_intent not in ("rag", "tool", "both", "chitchat"):
        final_intent = "chitchat"

    return {"intent": final_intent}
