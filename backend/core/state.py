"""Agent & RAG graph state definitions."""
from __future__ import annotations

from typing import Annotated, Literal, Optional, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


def merge_dicts(existing: dict, new: dict) -> dict:
    return {**existing, **new}


class ToolCall(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)
    tool_call_id: Optional[str] = None


class ToolResult(BaseModel):
    name: str
    args: dict
    result: Any = None
    error: Optional[str] = None
    tool_call_id: Optional[str] = None


class HitlReview(BaseModel):
    review_id: str
    thread_id: str
    tool_name: str
    tool_args: dict
    status: Literal["pending", "approved", "rejected", "modified", "expired"] = "pending"
    reason: str = ""


class RagState(TypedDict):
    user_query: str
    sub_queries: list[str]
    vector_docs: list[dict]
    bm25_docs: list[dict]
    rrf_docs: list[dict]
    reranked_docs: list[dict]
    context: str
    draft_answer: str
    inspect_trace: Annotated[dict, merge_dicts]


class ToolState(TypedDict):
    user_query: str
    thread_id: str
    tool_plan: list[dict]
    tool_results: list[dict]
    hitl_reviews: list[dict]
    iteration: int


class AgentState(dict):
    messages: list[BaseMessage]
    user_query: str
    thread_id: str
    user_id: str
    compressed_history: str
    conversation_summary: str
    rewritten_query: str
    intent: str
    tool_plan: list[dict]
    rag_context: str
    rag_draft: str
    tool_results: list[dict]
    hitl_reviews: list[dict]
    assembled_context: str
    final_answer: str
    metadata: dict