"""
creditsense/rag/vectorstore.py
------------------------------
Vector Store Abstraction Layer providing ChromaDB (primary) and TF-IDF (offline fallback)
semantic retrieval with rich policy metadata.
"""

from __future__ import annotations

import json
import logging
import pickle
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger("creditsense.rag.vectorstore")

ROOT = Path(__file__).parent.parent
VECTORSTORE_DIR = ROOT / "vectorstore"
METADATA_PATH = VECTORSTORE_DIR / "store_metadata.json"
TFIDF_STORE_PATH = VECTORSTORE_DIR / "tfidf_store.pkl"
CHROMA_COLLECTION = "lending_policy"


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    a = np.array(vec_a, dtype=float)
    b = np.array(vec_b, dtype=float)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class BaseRetriever(ABC):
    """Abstract interface for policy clause retrieval engines."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        top_k: int = 2,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve the top-k most relevant policy clauses for a given query."""
        pass


class ChromaRetriever(BaseRetriever):
    """Semantic vector store retriever backed by ChromaDB and SentenceTransformer."""

    def __init__(self, collection_name: str = CHROMA_COLLECTION, store_dir: Path = VECTORSTORE_DIR) -> None:
        import chromadb
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer("all-MiniLM-L6-v2")
        self._client = chromadb.PersistentClient(path=str(store_dir))
        self._collection = self._client.get_collection(collection_name)

    def retrieve(
        self,
        query: str,
        top_k: int = 2,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query_emb = self._model.encode([query], show_progress_bar=False).tolist()

        where_filter = {"category": category} if category else None

        results = self._collection.query(
            query_embeddings=query_emb,
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"],
        )

        clauses: List[Dict[str, Any]] = []
        if not results or not results["documents"] or not results["documents"][0]:
            return clauses

        for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            clauses.append({
                "id": meta.get("id", ""),
                "title": meta.get("title", ""),
                "category": meta.get("category", ""),
                "document": meta.get("document", ""),
                "section": meta.get("section", ""),
                "policy_type": meta.get("policy_type", ""),
                "version": meta.get("version", ""),
                "source": meta.get("source", ""),
                "text": doc,
                "score": round(1.0 - float(dist), 4) if dist is not None else 1.0,
            })
        return clauses


class TfidfRetriever(BaseRetriever):
    """Deterministic sparse TF-IDF retrieval backend for offline and $0 local execution."""

    def __init__(self, store_path: Path = TFIDF_STORE_PATH) -> None:
        if not store_path.exists():
            raise FileNotFoundError(
                f"TF-IDF store not found at {store_path}. Run: python -m rag.ingest"
            )
        with open(store_path, "rb") as f:
            store = pickle.load(f)
        self._vectorizer = store["vectorizer"]
        self._matrix = store["matrix"]
        self._clauses = store["clauses"]

    def retrieve(
        self,
        query: str,
        top_k: int = 2,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q_vec = self._vectorizer.transform([query]).toarray()[0]
        scores: List[tuple[int, float]] = []
        mat_dense = self._matrix.toarray()

        for idx, row in enumerate(mat_dense):
            clause = self._clauses[idx]
            if category and clause.get("category") != category:
                continue
            sim = _cosine_similarity(q_vec.tolist(), row.tolist())
            scores.append((idx, sim))

        scores.sort(key=lambda x: x[1], reverse=True)

        results: List[Dict[str, Any]] = []
        for idx, sim in scores[:top_k]:
            c = self._clauses[idx]
            results.append({
                "id": c.get("id", ""),
                "title": c.get("title", ""),
                "category": c.get("category", ""),
                "document": c.get("document", ""),
                "section": c.get("section", ""),
                "policy_type": c.get("policy_type", ""),
                "version": c.get("version", ""),
                "source": c.get("source", ""),
                "text": c.get("text", ""),
                "score": round(sim, 4),
            })
        return results


# ── Global Retriever Factory Singleton ───────────────────────────────────────
_RETRIEVER_INSTANCE: Optional[BaseRetriever] = None


def get_retriever(force_refresh: bool = False) -> BaseRetriever:
    """
    Factory function returning the active retriever instance (ChromaDB with TF-IDF fallback).
    """
    global _RETRIEVER_INSTANCE
    if _RETRIEVER_INSTANCE is not None and not force_refresh:
        return _RETRIEVER_INSTANCE

    # Read backend configuration if metadata exists
    backend = "sentence-transformers"
    if METADATA_PATH.exists():
        try:
            meta = json.loads(METADATA_PATH.read_text())
            backend = meta.get("backend", "sentence-transformers")
        except Exception:
            pass

    if backend == "sentence-transformers":
        try:
            _RETRIEVER_INSTANCE = ChromaRetriever(CHROMA_COLLECTION, VECTORSTORE_DIR)
            logger.info("Initialized ChromaDB vector store retriever.")
            return _RETRIEVER_INSTANCE
        except Exception as exc:
            logger.warning("ChromaDB initialization failed (%s). Falling back to TF-IDF retriever.", exc)

    # Fallback to TF-IDF
    _RETRIEVER_INSTANCE = TfidfRetriever(TFIDF_STORE_PATH)
    logger.info("Initialized TF-IDF sparse retriever.")
    return _RETRIEVER_INSTANCE
