"""API schemas — Pydantic models for request/response bodies."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    username: str
    role: str


class RegisterRequest(BaseModel):
    username: str
    password: str


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatResponse(BaseModel):
    thread_id: str
    answer: str
    metadata: dict = {}


class HitlReviewItem(BaseModel):
    review_id: str
    tool: str
    args: dict
    reason: str = ""


class HitlApproveRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject|modify)$")
    review_id: Optional[str] = None
    modified_args: Optional[dict] = None


class KBUploadRequest(BaseModel):
    kb_id: str = "default"
    title: str = ""
    content: str
    chunk_size: int = 800
    chunk_overlap: int = 100
    metadata: Optional[dict] = None


class KBDocumentInfo(BaseModel):
    doc_id: str
    title: str
    chunk_count: int
    metadata: dict = {}
    created_at: str = ""


class InspectRequest(BaseModel):
    kb_id: str = "default"
    query: str


class InspectResponse(BaseModel):
    query: str
    vector: dict = {}
    bm25: dict = {}
    rrf: dict = {}
    rerank: dict = {}
    context: str = ""
    draft_answer: str = ""
