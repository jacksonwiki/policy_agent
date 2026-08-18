"""Query rewrite node — coreference resolution + sub-question splitting."""
from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, SystemMessage

from ..state import AgentState
from ...llm import get_llm, TaskType

SYSTEM_PROMPT = """你是一个保险智能助手的查询改写专家。请根据对话历史（如果有）和当前用户问题，进行改写：

1. 指代消解：将"他/她/这个/那个"等指代词替换为具体内容
2. 子问题拆分：将复杂问题拆分为2-5个独立子问题（用于多路召回）
3. 同义词扩展：为每个子问题补充保险领域的同义词

输出JSON格式：
{
  "rewritten_query": "改写后的完整问题",
  "sub_queries": ["子问题1", "子问题2"],
  "synonyms": {"子问题1": ["同义词1", "同义词2"]}
}

如果无法拆分，sub_queries中只包含rewritten_query即可。"""


def rewrite_query(state: AgentState) -> dict:
    """Rewrite user query with context awareness and split into sub-queries."""
    user_query = state.get("user_query", "")
    compressed = state.get("compressed_history", "")

    context_text = f"\n\n对话历史摘要：\n{compressed}" if compressed else ""
    prompt = f"当前用户问题：{user_query}{context_text}"

    try:
        llm = get_llm(TaskType.LIGHT)
        response = llm.invoke([
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ])
        raw = response.content.strip()
    except Exception:
        raw = user_query

    rewritten = user_query
    sub_queries = [user_query]

    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1] if "\n" in raw else raw
        if raw.endswith("```"):
            raw = raw[:-3]

    try:
        parsed = json.loads(raw)
        candidate = parsed.get("rewritten_query", "")
        if candidate and len(candidate) > 2 and candidate != user_query:
            rewritten = candidate
        candidate_sub = parsed.get("sub_queries", [])
        if candidate_sub and len(candidate_sub) > 0:
            sub_queries = candidate_sub
    except json.JSONDecodeError:
        pass

    return {
        "rewritten_query": rewritten,
        "sub_queries": sub_queries,
    }
