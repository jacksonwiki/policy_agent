"""RAG sub-graph: query rewrite → multi-retrieval → RRF → rerank → context → draft."""
from __future__ import annotations

from typing import Any, Annotated, TypedDict

from langgraph.graph import StateGraph, END

from ...config import get_settings
from ...llm import get_llm, TaskType
from ...retrievers.vector import VectorRetriever
from ...retrievers.bm25 import BM25Retriever
from ...retrievers.rerank import Reranker


def _merge_inspect(existing: dict, new: dict) -> dict:
    return {**existing, **new}


class RagSubState(TypedDict):
    rewritten_query: str
    sub_queries: list[str]
    vector_docs: list[dict]
    bm25_docs: list[dict]
    rrf_docs: list[dict]
    reranked_docs: list[dict]
    context: str
    draft_answer: str
    inspect_trace: Annotated[dict, _merge_inspect]


def _rag_query_rewrite(state: RagSubState) -> dict:
    """Node 1: rewrite query + split into sub-queries for multi-retrieval."""
    from ...core.nodes.query_rewrite import rewrite_query

    # Reuse the same rewrite logic but with sub_queries output
    result = rewrite_query({
        "user_query": state.get("user_query", ""),
        "compressed_history": "",
        "messages": state.get("messages", []),
    })
    return {
        "rewritten_query": result.get("rewritten_query", state.get("user_query", "")),
        "sub_queries": result.get("sub_queries", [state.get("user_query", "")]),
    }


def _rag_vector_retrieval(state: RagSubState) -> dict:
    """Node 2a: parallel vector retrieval for each sub-query."""
    settings = get_settings()
    retriever = VectorRetriever()
    sub_queries = state.get("sub_queries", [state.get("rewritten_query", "")])

    all_docs: list[dict] = []
    seen_keys: set[str] = set()

    for sq in sub_queries:
        docs = retriever.retrieve(sq, top_k=settings.rag_top_k_retrieval)
        for d in docs:
            key = d.get("id", d.get("content", "")[:50])
            if key not in seen_keys:
                seen_keys.add(key)
                d["retrieval_source"] = "vector"
                all_docs.append(d)

    return {
        "vector_docs": all_docs,
        "inspect_trace": {**state.get("inspect_trace", {}), "vector_docs": all_docs[:10]},
    }


def _rag_bm25_retrieval(state: RagSubState) -> dict:
    """Node 2b: parallel BM25 retrieval for each sub-query."""
    try:
        retriever = BM25Retriever()
        sub_queries = state.get("sub_queries", [state.get("rewritten_query", "")])

        all_docs: list[dict] = []
        seen_keys: set[str] = set()

        for sq in sub_queries:
            docs = retriever.retrieve(sq, top_k=get_settings().rag_top_k_retrieval)
            for d in docs:
                key = d.get("id", d.get("content", "")[:50])
                if key not in seen_keys:
                    seen_keys.add(key)
                    d["retrieval_source"] = "bm25"
                    all_docs.append(d)

        return {
            "bm25_docs": all_docs,
            "inspect_trace": {**state.get("inspect_trace", {}), "bm25_docs": all_docs[:10]},
        }
    except Exception:
        # BM25 may not be initialised; return empty list gracefully
        return {
            "bm25_docs": [],
            "inspect_trace": {**state.get("inspect_trace", {}), "bm25_docs": []},
        }


def _rag_rrf_fusion(state: RagSubState) -> dict:
    """Node 3: Reciprocal Rank Fusion of vector + BM25 results."""
    settings = get_settings()
    k = settings.rag_rrf_k

    source_docs: dict[str, list[dict]] = {}
    if state.get("vector_docs"):
        source_docs["vector"] = state["vector_docs"]
    if state.get("bm25_docs"):
        source_docs["bm25"] = state["bm25_docs"]

    if not source_docs:
        return {"rrf_docs": [], "inspect_trace": {**state.get("inspect_trace", {}), "rrf_docs": []}}

    # Collect all unique docs with their ranks per source
    doc_scores: dict[str, float] = {}
    doc_data: dict[str, dict] = {}

    for source, docs in source_docs.items():
        for rank, doc in enumerate(docs, start=1):
            key = doc.get("id", doc.get("content", "")[:100])
            rrf_score = 1.0 / (k + rank)
            doc_scores[key] = doc_scores.get(key, 0.0) + rrf_score
            if key not in doc_data:
                doc_data[key] = doc

    # Sort by RRF score descending
    sorted_keys = sorted(doc_scores, key=lambda x: doc_scores[x], reverse=True)
    rrf_docs = []
    for key in sorted_keys[:settings.rag_top_k_rrf]:
        d = dict(doc_data[key])
        d["rrf_score"] = doc_scores[key]
        rrf_docs.append(d)

    return {
        "rrf_docs": rrf_docs,
        "inspect_trace": {**state.get("inspect_trace", {}), "rrf_docs": rrf_docs[:10]},
    }


def _rag_rerank(state: RagSubState) -> dict:
    """Node 4: cross-encoder rerank top candidates → final top-N."""
    settings = get_settings()
    rrf_docs = state.get("rrf_docs", [])

    if not rrf_docs:
        return {"reranked_docs": [], "inspect_trace": {**state.get("inspect_trace", {}), "reranked_docs": []}}

    try:
        reranker = Reranker()
        query = state.get("rewritten_query", state.get("user_query", ""))
        reranked = reranker.rerank(query, rrf_docs, top_k=settings.rerank_max_top_k)
    except Exception:
        # Fallback: take top-N from RRF
        reranked = rrf_docs[:settings.rerank_max_top_k]

    return {
        "reranked_docs": reranked,
        "inspect_trace": {**state.get("inspect_trace", {}), "reranked_docs": reranked},
    }


def _rag_assemble_context(state: RagSubState) -> dict:
    """Node 5: assemble final context from reranked docs with deduplication + truncation."""
    settings = get_settings()
    docs = state.get("reranked_docs", [])

    if not docs:
        return {"context": "（知识库中未找到相关内容）", "inspect_trace": {**state.get("inspect_trace", {}), "context": ""}}

    parts: list[str] = []
    total_tokens = 0
    for i, doc in enumerate(docs):
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})
        source = metadata.get("source", metadata.get("document_id", "unknown"))

        # Rough token estimate (4 chars ≈ 1 token for Chinese)
        est_tokens = len(content) // 4
        if total_tokens + est_tokens > settings.rag_max_context_tokens:
            break

        parts.append(f"[{i+1}] {content}\n(来源: {source})")
        total_tokens += est_tokens

    context = "\n\n".join(parts)
    return {
        "context": context,
        "inspect_trace": {**state.get("inspect_trace", {}), "context": context},
    }


def _rag_generate_draft(state: RagSubState) -> dict:
    """Node 6: generate a draft answer from the context (not final — main graph will merge tool data)."""
    context = state.get("context", "")
    user_query = state.get("user_query", "")

    if not context or context.startswith("（知识库中未找到"):
        return {"draft_answer": ""}

    llm = get_llm(TaskType.HEAVY)
    from langchain_core.messages import HumanMessage, SystemMessage

    prompt = f"""基于以下知识库内容回答用户问题。如果知识库内容不足，请明确说明。

用户问题：{user_query}

知识库内容：
{context}

请给出回答："""

    response = llm.invoke([
        SystemMessage(content="你是一个保险知识库问答助手。请严格依据提供的知识库内容回答，不要编造。"),
        HumanMessage(content=prompt),
    ])

    return {"draft_answer": response.content}


def build_rag_subgraph(checkpointer=None) -> StateGraph:
    """Construct the RAG sub-graph and return the compiled StateGraph.

    Entry point: call with {"user_query": str}
    Output keys: context, draft_answer, inspect_trace
    """
    graph = StateGraph(RagSubState)

    graph.add_node("rag_query_rewrite", _rag_query_rewrite)
    graph.add_node("rag_vector_retrieval", _rag_vector_retrieval)
    graph.add_node("rag_bm25_retrieval", _rag_bm25_retrieval)
    graph.add_node("rag_rrf_fusion", _rag_rrf_fusion)
    graph.add_node("rag_rerank", _rag_rerank)
    graph.add_node("rag_assemble_context", _rag_assemble_context)
    graph.add_node("rag_generate_draft", _rag_generate_draft)

    # Flow: rewrite → parallel(vector, bm25) → RRF → rerank → assemble → draft
    graph.add_edge("rag_query_rewrite", "rag_vector_retrieval")
    graph.add_edge("rag_query_rewrite", "rag_bm25_retrieval")
    graph.add_edge("rag_vector_retrieval", "rag_rrf_fusion")
    graph.add_edge("rag_bm25_retrieval", "rag_rrf_fusion")
    graph.add_edge("rag_rrf_fusion", "rag_rerank")
    graph.add_edge("rag_rerank", "rag_assemble_context")
    graph.add_edge("rag_assemble_context", "rag_generate_draft")
    graph.add_edge("rag_generate_draft", END)

    graph.set_entry_point("rag_query_rewrite")

    return graph.compile(checkpointer=checkpointer)