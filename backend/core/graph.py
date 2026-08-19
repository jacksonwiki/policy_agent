"""Main Agent graph — orchestrates RAG sub-graph + tool sub-graph + HITL.

Architecture:

    START → compress → rewrite → route_intent
         ┌─────────┬──────────┬──────────┐
         ↓         ↓          ↓          ↓
      chitchat   rag_path  tool_path  both_path
         │         │          │          │
         │    rag_subgraph  tool_subgraph │
         │         │          │          │
         │    merge_rag   merge_tool  (both run)
         │         │          │          │
         └──── assemble ──────┴──────────┘
                   ↓
            final_generate
                   ↓
                 END

For 'both' intent: rag_subgraph and tool_subgraph run in parallel via
LangGraph fan-out. assemble node only runs when both subgraphs complete
(LangGraph barrier synchronization).
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import StateGraph, END

from .state import AgentState
from .nodes import (
    compress_conversation,
    rewrite_query,
    route_intent,
    assemble_answer,
    generate_final_answer,
)
from .subgraphs import build_rag_subgraph, build_tool_subgraph


# ── Intent routing ────────────────────────────────────────
def _route_after_intent(state: AgentState) -> str:
    """Return the next node name based on intent."""
    intent = state.get("intent", "chitchat")
    if intent == "rag":
        return "rag_subgraph"
    elif intent == "tool":
        return "tool_subgraph"
    elif intent == "both":
        return "fanout_both"
    else:
        return "final_generate"


def _pass_through(state: AgentState) -> dict:
    """Pass-through node for fan-out."""
    return {}


def build_agent_graph(checkpointer=None) -> StateGraph:
    """Build and return the agent graph (not yet compiled).

    Call .compile(checkpointer=...) on the result to get a runnable graph.
    Passes checkpointer to subgraphs for HITL interrupt support.

    Implementation note: AgentState is a plain dict subclass, while the
    sub-graphs use TypedDict/dict subclasses. LangGraph's automatic state
    mapping between these heterogeneous state types is unreliable and can
    silently drop fields (e.g. ``user_query`` / ``sub_queries`` for the RAG
    sub-graph). We therefore wrap each sub-graph invocation in an explicit
    adapter node that copies the required fields in/out.
    """
    graph = StateGraph(AgentState)

    # ── Main nodes ──────────────────────────────────────
    graph.add_node("compress", compress_conversation)
    graph.add_node("rewrite", rewrite_query)
    graph.add_node("route_intent", route_intent)
    graph.add_node("assemble", assemble_answer)
    graph.add_node("final_generate", generate_final_answer)
    graph.add_node("fanout_both", _pass_through)

    # ── Sub-graphs (share checkpointer for HITL) ────────
    rag_sub = build_rag_subgraph(checkpointer=checkpointer)
    tool_sub = build_tool_subgraph(checkpointer=checkpointer)

    async def _rag_subgraph_node(state: AgentState) -> dict:
        """Explicitly bridge AgentState ↔ RagSubState to avoid field loss."""
        from .subgraphs.rag_subgraph import RagSubState

        user_query = state.get("user_query", "")
        sub_queries = state.get("sub_queries", [])
        if not sub_queries:
            sub_queries = [user_query] if user_query else []

        rag_input = RagSubState(
            user_query=user_query,
            rewritten_query=state.get("rewritten_query", user_query),
            sub_queries=sub_queries,
            vector_docs=[],
            bm25_docs=[],
            rrf_docs=[],
            reranked_docs=[],
            context="",
            draft_answer="",
            skip_draft=True,
            inspect_trace={},
        )

        result = await rag_sub.ainvoke(rag_input)
        # 主链路跳过草稿生成：直接映射原始知识 context 交给 assemble，
        # 最终答案由 final_generate 一次性生成（省一次 HEAVY LLM 调用）。
        context = result.get("context", "")
        if not context or context.startswith("（知识库中未找到"):
            context = ""
        return {
            "rag_context": context,
            "rag_draft": "",
        }

    async def _tool_subgraph_node(state: AgentState) -> dict:
        """Explicitly bridge AgentState ↔ ToolSubState to avoid field loss."""
        from .subgraphs.tool_subgraph import ToolSubState

        tool_input = ToolSubState(
            user_query=state.get("user_query", ""),
            thread_id=state.get("thread_id", ""),
            tool_plan=[],
            tool_results=[],
            hitl_reviews=[],
            iteration=0,
        )

        result = await tool_sub.ainvoke(tool_input)
        return {
            "tool_results": result.get("tool_results", []),
            "hitl_reviews": result.get("hitl_reviews", []),
        }

    graph.add_node("rag_subgraph", _rag_subgraph_node)
    graph.add_node("tool_subgraph", _tool_subgraph_node)

    # ── Entry & main flow ──────────────────────────────
    graph.set_entry_point("compress")
    graph.add_edge("compress", "rewrite")
    graph.add_edge("rewrite", "route_intent")

    # ── Conditional routing from route_intent ──────────
    graph.add_conditional_edges(
        "route_intent",
        _route_after_intent,
        {
            "rag_subgraph": "rag_subgraph",
            "tool_subgraph": "tool_subgraph",
            "final_generate": "final_generate",
            "fanout_both": "fanout_both",
        },
    )

    # ── Fan-out for 'both' intent ───────────────────────
    # fanout_both → both rag_subgraph AND tool_subgraph
    graph.add_edge("fanout_both", "rag_subgraph")
    graph.add_edge("fanout_both", "tool_subgraph")

    # ── After RAG subgraph ──────────────────────────────
    graph.add_edge("rag_subgraph", "assemble")

    # ── After tool subgraph ─────────────────────────────
    graph.add_edge("tool_subgraph", "assemble")

    # ── Final path ─────────────────────────────────────
    graph.add_edge("assemble", "final_generate")
    graph.add_edge("final_generate", END)

    return graph
