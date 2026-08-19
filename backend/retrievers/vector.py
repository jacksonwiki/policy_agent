"""Vector retriever with ChromaDB backend."""
from __future__ import annotations

import hashlib
import re
import threading
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..llm.embeddings import get_embeddings


_project_root = Path(__file__).resolve().parent.parent.parent
_chroma_dir = _project_root / "data" / "chroma"


def _content_fingerprint(text: str) -> str:
    """内容指纹：去除空白后取 MD5，用于跨文档内容级去重。

    同一文档重复上传（或内容完全相同的两个 chunk）会得到相同指纹，
    在融合/去重环节用于合并，避免 RRF 分数叠加导致结果失真。
    """
    normalized = re.sub(r"\s+", "", text or "").strip()
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()


def _doc_key(doc: dict) -> str:
    """检索结果的去重键：优先用内容指纹，空内容回退到 id。"""
    content = doc.get("content", "")
    if content and content.strip():
        return f"content:{_content_fingerprint(content)}"
    return f"id:{doc.get('id', '')}"


class VectorRetriever:
    """Vector similarity search with ChromaDB, falling back to in-memory store.

    Uses class-level shared state so that when Chroma is unavailable,
    all instances share the same in-memory document store.
    """

    _shared_in_memory_docs: list[dict] = []
    _shared_collection: Any = None
    _shared_client: Any = None
    _chroma_available: bool | None = None
    # 多线程并发检索（sub_queries 并行召回）时，首次建连可能被多个线程
    # 同时触发，必须加锁防止重复创建 PersistentClient 导致连接损坏。
    _connection_lock = threading.Lock()

    def __init__(self) -> None:
        self._embeddings = get_embeddings()
        self._settings = get_settings()

    @property
    def _collection(self) -> Any:
        return VectorRetriever._shared_collection

    @_collection.setter
    def _collection(self, value: Any) -> None:
        VectorRetriever._shared_collection = value

    @property
    def _chroma_client(self) -> Any:
        return VectorRetriever._shared_client

    @_chroma_client.setter
    def _chroma_client(self, value: Any) -> None:
        VectorRetriever._shared_client = value

    @property
    def _in_memory_docs(self) -> list[dict]:
        return VectorRetriever._shared_in_memory_docs

    @_in_memory_docs.setter
    def _in_memory_docs(self, value: list[dict]) -> None:
        VectorRetriever._shared_in_memory_docs = value

    @property
    def chroma_available(self) -> bool:
        if VectorRetriever._chroma_available is not None:
            return VectorRetriever._chroma_available
        try:
            import chromadb

            VectorRetriever._chroma_available = True
        except ImportError:
            VectorRetriever._chroma_available = False
        return VectorRetriever._chroma_available

    def _ensure_connection(self) -> None:
        if not self.chroma_available:
            return
        if self._collection is not None:
            return

        # double-checked locking：避免多线程同时进入建连逻辑
        with VectorRetriever._connection_lock:
            if self._collection is not None:
                return

            try:
                import chromadb
                from chromadb.config import Settings as ChromaSettings

                _chroma_dir.mkdir(parents=True, exist_ok=True)

                self._chroma_client = chromadb.PersistentClient(
                    path=str(_chroma_dir),
                    settings=ChromaSettings(anonymized_telemetry=False),
                )

                collection_name = self._settings.chroma_collection

                self._collection = self._chroma_client.get_or_create_collection(
                    name=collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                print(f"[chroma] Connection failed: {e}")
                self._chroma_available = False

    def retrieve(self, query: str, top_k: int = 20, min_score: float = 0.3) -> list[dict]:
        self._ensure_connection()

        if self._collection is None or self._collection.count() == 0:
            return self._retrieve_in_memory(query, top_k, min_score)

        try:
            query_embedding = self._embeddings.embed_query(query)
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )

            docs: list[dict] = []
            ids = results.get("ids", [[]])[0]
            distances = results.get("distances", [[]])[0]
            documents = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]

            for i in range(len(ids)):
                score = 1.0 - distances[i] if i < len(distances) else 0.0
                if score < min_score:
                    continue
                docs.append({
                    "id": ids[i],
                    "content": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "score": score,
                })
            return docs
        except Exception:
            return self._retrieve_in_memory(query, top_k, min_score)

    def _retrieve_in_memory(self, query: str, top_k: int, min_score: float = 0.3) -> list[dict]:
        if not self._in_memory_docs:
            return []

        try:
            query_embedding = self._embeddings.embed_query(query)
        except Exception:
            return []

        scored_docs = []
        for doc in self._in_memory_docs:
            doc_embedding = doc.get("_embedding")
            if doc_embedding is None:
                scored_docs.append({
                    "id": doc.get("id", ""),
                    "content": doc.get("content", ""),
                    "metadata": doc.get("metadata", {}),
                    "score": 0.0,
                })
                continue

            similarity = self._cosine_similarity(query_embedding, doc_embedding)
            if similarity < min_score:
                continue
            scored_docs.append({
                "id": doc.get("id", ""),
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {}),
                "score": similarity,
            })

        scored_docs.sort(key=lambda x: x["score"], reverse=True)
        return scored_docs[:top_k]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def add_documents(self, documents: list[dict]) -> None:
        if not documents:
            return

        # 内容级去重：跳过已在库中或本批内重复的内容，防止重复文档
        # 在 RRF 融合阶段分数叠加、挤占正确结果。
        existing_fps: set[str] = set()
        try:
            for d in self.get_all_documents():
                existing_fps.add(_content_fingerprint(d.get("content", "")))
        except Exception:
            pass

        unique: list[dict] = []
        for d in documents:
            fp = _content_fingerprint(d.get("content", ""))
            if not fp or fp in existing_fps:
                continue
            existing_fps.add(fp)
            unique.append(d)

        if not unique:
            return
        documents = unique

        self._ensure_connection()

        if self._collection is None:
            try:
                contents = [d["content"] for d in documents]
                embeddings = self._embeddings.embed_documents(contents)
                for doc, emb in zip(documents, embeddings):
                    self._in_memory_docs.append({
                        **doc,
                        "_embedding": emb,
                    })
            except Exception:
                for doc in documents:
                    self._in_memory_docs.append(doc)
            return

        try:
            ids = [d["id"] for d in documents]
            contents = [d["content"] for d in documents]
            metadatas = [d.get("metadata", {}) for d in documents]
            embeddings = self._embeddings.embed_documents(contents)

            self._collection.upsert(
                ids=ids,
                documents=contents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
        except Exception as e:
            print(f"[chroma] add_documents failed: {e}")
            for doc in documents:
                self._in_memory_docs.append(doc)

    def delete_documents(self, ids: list[str]) -> None:
        self._in_memory_docs = [
            d for d in self._in_memory_docs
            if not any(d.get("id", "").startswith(prefix) for prefix in ids)
        ]

        if self._collection is not None:
            try:
                all_ids = self._collection.get(include=[])
                matching = [
                    i for i in all_ids.get("ids", [])
                    if any(i.startswith(prefix) for prefix in ids)
                ]
                if matching:
                    self._collection.delete(ids=matching)
            except Exception:
                pass

    def count(self) -> int:
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return len(self._in_memory_docs)

    def get_all_documents(self) -> list[dict]:
        """Load all documents from Chroma for BM25 indexing."""
        self._ensure_connection()

        if self._collection is None or self._collection.count() == 0:
            return list(self._in_memory_docs)

        try:
            results = self._collection.get(include=["documents", "metadatas"])
            docs = []
            ids = results.get("ids", [])
            documents = results.get("documents", [])
            metadatas = results.get("metadatas", [])

            for i in range(len(ids)):
                docs.append({
                    "id": ids[i],
                    "content": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                })
            return docs
        except Exception:
            return list(self._in_memory_docs)