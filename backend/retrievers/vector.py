"""Vector retriever with ChromaDB backend."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import get_settings
from ..llm.embeddings import get_embeddings


_project_root = Path(__file__).resolve().parent.parent.parent
_chroma_dir = _project_root / "data" / "chroma"


class VectorRetriever:
    """Vector similarity search with ChromaDB, falling back to in-memory store."""

    def __init__(self) -> None:
        self._chroma_client: Any = None
        self._collection: Any = None
        self._embeddings = get_embeddings()
        self._settings = get_settings()
        self._in_memory_docs: list[dict] = []
        self._chroma_available: bool | None = None

    @property
    def chroma_available(self) -> bool:
        if self._chroma_available is not None:
            return self._chroma_available
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            self._chroma_available = True
        except ImportError:
            self._chroma_available = False
        return self._chroma_available

    def _ensure_connection(self) -> None:
        if not self.chroma_available:
            return
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

    def retrieve(self, query: str, top_k: int = 20) -> list[dict]:
        self._ensure_connection()

        if self._collection is None or self._collection.count() == 0:
            return self._retrieve_in_memory(query, top_k)

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
                docs.append({
                    "id": ids[i],
                    "content": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if i < len(metadatas) else {},
                    "score": score,
                })
            return docs
        except Exception:
            return self._retrieve_in_memory(query, top_k)

    def _retrieve_in_memory(self, query: str, top_k: int) -> list[dict]:
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
        self._in_memory_docs = [d for d in self._in_memory_docs if d.get("id") not in ids]

        if self._collection is not None:
            try:
                self._collection.delete(ids=ids)
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
