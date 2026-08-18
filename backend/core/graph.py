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


# ── Merge helpers ─────────────────────────────────────────
def _merge_rag_result(state: dict) -> dict:
    """Extract RAG sub-graph outputs into the main agent state."""
    return {
        "rag_context": state.get("context", ""),
        "rag_draft": state.get("draft_answer", ""),
    }


def _merge_tool_result(state: dict) -> dict:
    """Extract tool sub-graph outputs into the main agent state."""
    return {
        "tool_results": state.get("tool_results", []),
    }


def _pass_through(state: dict) -> dict:
    """Pass-through node for fan-out."""
    return {}


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


def _after_fanout_both(state: AgentState) -> str:
    """Route from fanout node to both subgraphs."""
    return "rag_subgraph"


def _after_fanout_both_tool(state: AgentState) -> str:
    """Route from fanout node to tool subgraph."""
    return "tool_subgraph"


def build_agent_graph(checkpointer=None) -> StateGraph:
    """Build and return the agent graph (not yet compiled).

    Call .compile(checkpointer=...) on the result to get a runnable graph.
    Passes checkpointer to subgraphs for HITL interrupt support.
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

    graph.add_node("rag_subgraph", rag_sub)
    graph.add_node("tool_subgraph", tool_sub)

    # Merge nodes
    graph.add_node("merge_rag", _merge_rag_result)
    graph.add_node("merge_tool", _merge_tool_result)

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
    graph.add_edge("rag_subgraph", "merge_rag")
    graph.add_edge("merge_rag", "assemble")

    # ── After tool subgraph ─────────────────────────────
    graph.add_edge("tool_subgraph", "merge_tool")
    graph.add_edge("merge_tool", "assemble")

    # ── Final path ─────────────────────────────────────
    graph.add_edge("assemble", "final_generate")
    graph.add_edge("final_generate", END)

    return graph
