"""FastAPI routes — chat SSE, HITL, KB management, RAG inspect."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from ..core.graph import build_agent_graph
from ..core.checkpointer import get_checkpointer
from ..core.state import AgentState
from .auth import UserStore, create_token, verify_token
from .schemas import (
    ChatRequest,
    HitlApproveRequest,
    InspectRequest,
    InspectResponse,
    KBUploadRequest,
)

router = APIRouter()

_agent_graph = None
_agent_graph_lock = threading.Lock()

_kb_documents: dict[str, list[dict]] = {}

_user_conversations: dict[str, list[dict]] = {}


def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        with _agent_graph_lock:
            if _agent_graph is None:
                checkpointer = get_checkpointer()
                graph = build_agent_graph(checkpointer=checkpointer)
                _agent_graph = graph.compile(checkpointer=checkpointer)
    return _agent_graph


async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header[7:]
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


@router.post("/auth/login")
async def login(req: Request, body: dict):
    username = body.get("username", "")
    password = body.get("password", "")
    if not UserStore.verify_password(username, password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user = UserStore.get_user(username)
    token = create_token(username, user["role"])
    return {"token": token, "username": username, "role": user["role"]}


@router.post("/auth/register")
async def register(body: dict):
    username = body.get("username", "")
    password = body.get("password", "")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")

    success = UserStore.create_user(username, password)
    if not success:
        raise HTTPException(status_code=400, detail="Username already exists")

    user = UserStore.get_user(username)
    token = create_token(username, user["role"])
    return {"token": token, "username": username, "role": user["role"]}


@router.get("/auth/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/chat")
async def chat(body: ChatRequest, current_user: dict = Depends(get_current_user)):
    """Chat with the agent via SSE streaming.

    Events emitted:
    - token: {content} — streamed LLM tokens during final answer generation
    - hitl_review: {review_id, tool, args, reason} — human-in-the-loop review
    - done: {answer, thread_id, intent} — final answer (full text, includes streamed tokens)
    - error: {message} — error event
    """
    agent = get_agent_graph()

    thread_id = body.thread_id or str(uuid.uuid4())
    user_id = current_user.get("sub", body.user_id or "anonymous")

    # Track conversation for this user
    convs = _user_conversations.setdefault(user_id, [])
    existing = next((c for c in convs if c["thread_id"] == thread_id), None)
    if existing:
        existing["updated_at"] = datetime.now().isoformat()
        existing["last_message"] = body.message[:50]
    else:
        convs.insert(0, {
            "thread_id": thread_id,
            "title": body.message[:30] or "新对话",
            "last_message": body.message[:50],
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        })

    # Load previous state from checkpointer to accumulate messages
    config = {"configurable": {"thread_id": thread_id}}
    previous_messages = []
    try:
        state = await agent.aget_state(config)
        if state is not None and state.values:
            prev_msgs = state.values.get("messages", [])
            if prev_msgs:
                previous_messages = list(prev_msgs)
    except Exception:
        pass

    new_message = {"type": "human", "content": body.message}
    all_messages = previous_messages + [new_message]

    initial_state: AgentState = {
        "messages": all_messages,
        "user_query": body.message,
        "thread_id": thread_id,
        "user_id": user_id,
        "compressed_history": "",
        "rewritten_query": "",
        "intent": "unknown",
        "tool_plan": [],
        "rag_context": "",
        "rag_draft": "",
        "tool_results": [],
        "hitl_reviews": [],
        "final_answer": "",
        "metadata": {},
    }

    async def event_generator() -> AsyncIterator[dict]:
        thread_config = {"configurable": {"thread_id": thread_id}}

        try:
            result = await agent.ainvoke(initial_state, config=thread_config)

            if "__interrupt__" in result:
                interrupt_data = result["__interrupt__"]
                hitl_payload = {
                    "review_id": "",
                    "tool": "",
                    "args": {},
                    "reason": "",
                }
                if isinstance(interrupt_data, list) and interrupt_data:
                    interrupt = interrupt_data[0]
                    if hasattr(interrupt, 'value'):
                        value = interrupt.value
                        hitl_payload = {
                            "review_id": value.get("review_id", ""),
                            "tool": value.get("tool", ""),
                            "args": value.get("args", {}),
                            "reason": value.get("reason", ""),
                        }
                elif isinstance(interrupt_data, dict):
                    hitl_payload = {
                        "review_id": interrupt_data.get("review_id", ""),
                        "tool": interrupt_data.get("tool", ""),
                        "args": interrupt_data.get("args", {}),
                        "reason": interrupt_data.get("reason", ""),
                    }

                yield {
                    "event": "hitl_review",
                    "data": json.dumps(hitl_payload, ensure_ascii=False),
                }
                yield {
                    "event": "done",
                    "data": json.dumps({
                        "answer": "（请先完成人工审核后继续对话）",
                        "thread_id": thread_id,
                        "intent": "hitl_pending",
                    }, ensure_ascii=False),
                }
                return

            answer = result.get("final_answer", "")
            if not answer:
                answer = result.get("rag_draft", "")
            if not answer:
                tool_results = result.get("tool_results", [])
                if tool_results:
                    answer = f"已完成 {len(tool_results)} 个工具调用。"
            if not answer:
                answer = "抱歉，我无法回答您的问题。"

            # Stream answer character-by-character for typewriter effect
            import asyncio
            CHUNK_SIZE = 2
            for i in range(0, len(answer), CHUNK_SIZE):
                chunk = answer[i : i + CHUNK_SIZE]
                yield {
                    "event": "token",
                    "data": json.dumps({"content": chunk}, ensure_ascii=False),
                }
                await asyncio.sleep(0.015)

            yield {
                "event": "done",
                "data": json.dumps({
                    "answer": answer,
                    "thread_id": thread_id,
                    "intent": result.get("intent", ""),
                }, ensure_ascii=False),
            }

        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"message": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())


@router.post("/chat/{thread_id}/approve")
async def approve_hitl(
    thread_id: str,
    body: HitlApproveRequest,
    current_user: dict = Depends(get_current_user),
):
    """Approve/reject/modify a HITL review and resume the agent graph."""
    agent = get_agent_graph()

    human_decision = {
        "action": body.action,
        "modified_args": body.modified_args,
    }

    config = {
        "configurable": {"thread_id": thread_id},
    }

    from langgraph.types import Command
    result = await agent.ainvoke(Command(resume=human_decision), config=config)

    answer = result.get("final_answer", "")
    if not answer:
        answer = result.get("rag_draft", "")
    if not answer:
        tool_results = result.get("tool_results", [])
        if tool_results:
            answer = f"工具执行完成，共 {len(tool_results)} 个步骤。"

    return {
        "thread_id": thread_id,
        "status": "resumed",
        "answer": answer,
        "intent": result.get("intent", ""),
    }


@router.get("/chat/conversations")
async def list_conversations(current_user: dict = Depends(get_current_user)):
    """List all conversations for the current user."""
    user_id = current_user.get("sub", "anonymous")
    convs = _user_conversations.get(user_id, [])

    # Also try to restore from checkpointer for threads with data
    agent = get_agent_graph()
    saver = get_checkpointer()
    config = {"configurable": {"thread_id": "__list__"}}

    # Build enriched list — try to get state for each thread
    enriched = []
    for conv in convs:
        thread_id = conv["thread_id"]
        state_config = {"configurable": {"thread_id": thread_id}}
        try:
            state = await agent.aget_state(state_config)
            if state is not None and state.values:
                msgs = state.values.get("messages", [])
                # Count messages to show activity
                msg_count = len(msgs) if msgs else 0
                conv_with_count = {**conv, "message_count": msg_count}
                enriched.append(conv_with_count)
            else:
                enriched.append({**conv, "message_count": 0})
        except Exception:
            enriched.append({**conv, "message_count": 0})

    return {"conversations": enriched, "total": len(enriched)}


@router.get("/chat/history/{thread_id}")
async def get_chat_history(
    thread_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get the message history for a specific thread."""
    agent = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = await agent.aget_state(config)
        if state is None or not state.values:
            return {"thread_id": thread_id, "messages": [], "intent": ""}

        values = state.values
        messages = values.get("messages", [])

        # Format messages for frontend
        formatted = []
        for msg in messages:
            msg_type = msg.get("type", "") if isinstance(msg, dict) else getattr(msg, "type", "")
            content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
            if msg_type in ("human", "user"):
                formatted.append({"role": "user", "content": content})
            elif msg_type in ("ai", "assistant"):
                formatted.append({"role": "assistant", "content": content})
            elif msg_type == "tool":
                formatted.append({"role": "tool", "content": str(content)})

        return {
            "thread_id": thread_id,
            "messages": formatted,
            "intent": values.get("intent", ""),
        }
    except Exception:
        return {"thread_id": thread_id, "messages": [], "intent": ""}


@router.delete("/chat/conversations/{thread_id}")
async def delete_conversation(
    thread_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a conversation."""
    user_id = current_user.get("sub", "anonymous")
    convs = _user_conversations.get(user_id, [])
    _user_conversations[user_id] = [c for c in convs if c["thread_id"] != thread_id]

    # Note: checkpointer data cleanup is not straightforward
    # For now we just remove from the tracking list
    return {"status": "deleted", "thread_id": thread_id}


@router.post("/kb/upload")
async def upload_document(body: KBUploadRequest, current_user: dict = Depends(get_current_user)):
    """Upload a document to the RAG knowledge base."""
    kb_id = body.kb_id
    if kb_id not in _kb_documents:
        _kb_documents[kb_id] = []

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    created_at = datetime.now().isoformat()

    doc = {
        "doc_id": doc_id,
        "title": body.title or "未命名文档",
        "content": body.content,
        "chunk_count": max(1, len(body.content) // body.chunk_size),
        "metadata": body.metadata or {},
        "created_at": created_at,
    }

    _kb_documents[kb_id].append(doc)

    try:
        from ..retrievers.vector import VectorRetriever
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=body.chunk_size,
            chunk_overlap=body.chunk_overlap,
        )
        chunks = splitter.split_text(body.content)

        docs = []
        for i, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_chunk_{i}"
            docs.append({
                "id": chunk_id,
                "content": chunk,
                "metadata": {
                    "source": doc_id,
                    "title": body.title,
                    "chunk_index": i,
                    "kb_id": kb_id,
                },
            })

        retriever = VectorRetriever()
        retriever.add_documents(docs)
        doc["chunk_count"] = len(chunks)
    except Exception as e:
        pass

    return {
        "doc_id": doc_id,
        "title": doc["title"],
        "chunk_count": doc["chunk_count"],
        "created_at": created_at,
    }


@router.get("/kb/documents")
async def list_documents(kb_id: str = "default", current_user: dict = Depends(get_current_user)):
    """List all documents in the KB."""
    docs = _kb_documents.get(kb_id, [])
    return {
        "documents": [
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "chunk_count": d["chunk_count"],
                "created_at": d["created_at"],
            }
            for d in docs
        ],
        "total": len(docs),
    }


@router.delete("/kb/documents/{doc_id}")
async def delete_document(doc_id: str, kb_id: str = "default", current_user: dict = Depends(get_current_user)):
    """Delete a document from the KB."""
    docs = _kb_documents.get(kb_id, [])
    _kb_documents[kb_id] = [d for d in docs if d["doc_id"] != doc_id]

    try:
        from ..retrievers.vector import VectorRetriever
        retriever = VectorRetriever()
        retriever.delete_documents([doc_id])
    except Exception:
        pass

    return {"status": "deleted", "doc_id": doc_id}


@router.post("/rag/inspect")
async def inspect_rag(body: InspectRequest, current_user: dict = Depends(get_current_user)):
    """Run a RAG query and return every intermediate step for debugging."""
    from ..core.subgraphs.rag_subgraph import build_rag_subgraph

    rag = build_rag_subgraph()

    initial_input = {
        "user_query": body.query,
        "rewritten_query": "",
        "sub_queries": [],
        "vector_docs": [],
        "bm25_docs": [],
        "rrf_docs": [],
        "reranked_docs": [],
        "context": "",
        "draft_answer": "",
        "inspect_trace": {},
    }

    try:
        result = await rag.ainvoke(initial_input)
    except Exception as e:
        result = initial_input

    trace = result.get("inspect_trace", {})

    vector_results = trace.get("vector_docs", [])
    bm25_results = trace.get("bm25_docs", [])
    rrf_results = trace.get("rrf_docs", [])
    rerank_results = trace.get("reranked_docs", [])

    vector_formatted = [
        {"id": d.get("id", i), "score": d.get("score", 0), "content": d.get("content", "")}
        for i, d in enumerate(vector_results)
    ]
    bm25_formatted = [
        {"id": d.get("id", i), "score": d.get("score", 0), "content": d.get("content", "")}
        for i, d in enumerate(bm25_results)
    ]
    rrf_formatted = [
        {"id": d.get("id", i), "score": d.get("score", 0), "content": d.get("content", "")}
        for i, d in enumerate(rrf_results)
    ]
    rerank_formatted = [
        {"id": d.get("id", i), "score": d.get("score", 0), "content": d.get("content", "")}
        for i, d in enumerate(rerank_results)
    ]

    return InspectResponse(
        query=body.query,
        vector={"results": vector_formatted},
        bm25={"results": bm25_formatted},
        rrf={"results": rrf_formatted},
        rerank={"results": rerank_formatted},
        context=result.get("context", ""),
        draft_answer=result.get("draft_answer", ""),
    )


@router.get("/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return {"users": UserStore.list_users()}


@router.put("/users/{username}/role")
async def update_user_role(
    username: str,
    body: dict,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    role = body.get("role", "user")
    success = UserStore.update_role(username, role)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"username": username, "role": role}


@router.delete("/users/{username}")
async def delete_user(
    username: str,
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    success = UserStore.delete_user(username)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "deleted", "username": username}
