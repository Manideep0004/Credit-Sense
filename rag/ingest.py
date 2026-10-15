"""
creditsense/rag/ingest.py
-------------------------
Policy ingestion pipeline: extracts policy texts, prepares structured metadata,
computes embeddings, and writes to ChromaDB and TF-IDF persistent vector stores.

Usage:
    python -m rag.ingest
    python -m rag.ingest --force-tfidf
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

# Add package root to sys.path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.corpus import POLICY_CLAUSES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("creditsense.rag.ingest")

VECTORSTORE_DIR = ROOT / "vectorstore"
VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_COLLECTION = "lending_policy"
TFIDF_STORE_PATH = VECTORSTORE_DIR / "tfidf_store.pkl"
METADATA_PATH = VECTORSTORE_DIR / "store_metadata.json"


def _try_sentence_transformers() -> Tuple[Callable[[List[str]], List[List[float]]], str]:
    """Load SentenceTransformer embedding model."""
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed_fn(texts: List[str]) -> List[List[float]]:
        return model.encode(texts, show_progress_bar=False).tolist()

    return embed_fn, "sentence-transformers"


def _build_tfidf_store(clauses: List[Dict[str, Any]]) -> Tuple[Callable[[List[str]], List[List[float]]], str]:
    """Fit TF-IDF vectorizer on policy clauses and serialize to disk."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts = [c["text"] for c in clauses]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=5000)
    matrix = vectorizer.fit_transform(texts)

    with open(TFIDF_STORE_PATH, "wb") as f:
        pickle.dump(
            {
                "vectorizer": vectorizer,
                "matrix": matrix,
                "clauses": clauses,
            },
            f,
        )
    logger.info("Persisted TF-IDF sparse store to %s", TFIDF_STORE_PATH)

    def embed_fn(query_texts: List[str]) -> List[List[float]]:
        return vectorizer.transform(query_texts).toarray().tolist()

    return embed_fn, "tfidf-sklearn"


def ingest_policy_corpus(
    force_tfidf: bool = False,
    collection_name: str = CHROMA_COLLECTION,
) -> Dict[str, Any]:
    """
    Execute full ingestion: chunking, metadata extraction, embedding, and vector persistence.
    """
    clauses = POLICY_CLAUSES
    logger.info("Starting ingestion of %d policy clauses.", len(clauses))

    texts = [c["text"] for c in clauses]
    ids = [c["id"] for c in clauses]
    metadatas = [
        {
            "id": c["id"],
            "title": c["title"],
            "category": c["category"],
            "document": c["document"],
            "section": c["section"],
            "policy_type": c["policy_type"],
            "version": c["version"],
            "source": c["source"],
        }
        for c in clauses
    ]

    # Always generate and save TF-IDF fallback store first
    _build_tfidf_store(clauses)

    backend = "tfidf-sklearn"
    if not force_tfidf:
        try:
            embed_fn, backend = _try_sentence_transformers()
            logger.info("Generating embeddings using: %s", backend)
            embeddings = embed_fn(texts)

            # Persist to ChromaDB
            import chromadb

            client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
            try:
                client.delete_collection(collection_name)
            except Exception:
                pass

            collection = client.create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
            logger.info("Successfully indexed %d clauses in ChromaDB collection '%s'.", len(ids), collection_name)
        except Exception as exc:
            logger.warning("ChromaDB ingestion failed (%s). TF-IDF fallback remains active.", exc)
            backend = "tfidf-sklearn"
    else:
        logger.info("Forced TF-IDF sparse backend.")

    # Write store metadata JSON
    meta = {
        "backend": backend,
        "chroma_collection": collection_name,
        "tfidf_store_path": str(TFIDF_STORE_PATH),
        "clause_count": len(clauses),
        "clause_ids": ids,
    }
    METADATA_PATH.write_text(json.dumps(meta, indent=2))
    logger.info("Store metadata saved to %s", METADATA_PATH)

    return meta


def main():
    parser = argparse.ArgumentParser(description="Ingest lending and AML policy corpus into vector store.")
    parser.add_argument("--force-tfidf", action="store_true", help="Force TF-IDF backend without downloading transformer weights")
    args = parser.parse_args()

    meta = ingest_policy_corpus(force_tfidf=args.force_tfidf)
    print("\n" + "=" * 50)
    print("CreditSense — RAG Policy Ingestion Complete")
    print("=" * 50)
    print(f"  Active Backend : {meta['backend']}")
    print(f"  Clauses Indexed: {meta['clause_count']}")
    print(f"  Clause IDs     : {', '.join(meta['clause_ids'])}")
    print("=" * 50)


if __name__ == "__main__":
    main()
