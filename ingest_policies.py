"""
ingest_policies.py
------------------
Embeds the policy corpus into ChromaDB (persistent local vector store).

Strategy:
  1. Try to use SentenceTransformer ('all-MiniLM-L6-v2') for embeddings.
  2. If sentence-transformers or HuggingFace is unavailable, fall back to
     TfidfVectorizer from scikit-learn and persist embeddings as numpy arrays
     in vectorstore/tfidf_store.pkl.
     NOTE: The TF-IDF path is a development/offline stand-in.
           Swap in real sentence-transformer embeddings for production.

Run:
    python ingest_policies.py
"""

import json
import pickle
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from data.policy_corpus import POLICY_CLAUSES

VECTORSTORE_DIR = ROOT / "vectorstore"
VECTORSTORE_DIR.mkdir(parents=True, exist_ok=True)

CHROMA_COLLECTION = "lending_policy"
TFIDF_STORE_PATH = VECTORSTORE_DIR / "tfidf_store.pkl"
METADATA_PATH = VECTORSTORE_DIR / "store_metadata.json"


# ── embedding backends ────────────────────────────────────────────────────────

def _try_sentence_transformers():
    """Return (embedding_fn, backend_name) or raise ImportError."""
    from sentence_transformers import SentenceTransformer  # noqa: F401
    model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(texts: list[str]) -> list[list[float]]:
        return model.encode(texts, show_progress_bar=False).tolist()

    return embed, "sentence-transformers"


def _tfidf_backend():
    """TF-IDF fallback. Returns (embedding_fn, backend_name)."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    # NOTE: TF-IDF is a swappable stand-in for production-grade embeddings.
    #       Replace with SentenceTransformer or an API embedding in production.
    texts = [c["text"] for c in POLICY_CLAUSES]
    vectorizer = TfidfVectorizer()
    matrix = vectorizer.fit_transform(texts)

    def embed(query_texts: list[str]) -> list[list[float]]:
        return vectorizer.transform(query_texts).toarray().tolist()

    # Persist vectorizer + matrix for later retrieval
    with open(TFIDF_STORE_PATH, "wb") as f:
        pickle.dump(
            {
                "vectorizer": vectorizer,
                "matrix": matrix,
                "clauses": POLICY_CLAUSES,
            },
            f,
        )
    return embed, "tfidf-sklearn"


# ── ingestion ─────────────────────────────────────────────────────────────────

def ingest(force_tfidf: bool = False):
    """Embed all policy clauses and persist to vector store."""
    texts = [c["text"] for c in POLICY_CLAUSES]
    ids = [c["id"] for c in POLICY_CLAUSES]

    # Choose embedding backend
    if force_tfidf:
        embed_fn, backend = _tfidf_backend()
        print(f"[INFO] Using embedding backend: {backend} (forced)")
    else:
        try:
            embed_fn, backend = _try_sentence_transformers()
            print(f"[INFO] Using embedding backend: {backend}")
        except Exception as e:
            print(f"[WARN] SentenceTransformer unavailable ({e}). Falling back to TF-IDF.")
            embed_fn, backend = _tfidf_backend()

    # Embed
    embeddings = embed_fn(texts)

    # Persist to ChromaDB if sentence-transformers is available
    if backend == "sentence-transformers":
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(VECTORSTORE_DIR))
            # Delete existing collection if reingesting
            try:
                client.delete_collection(CHROMA_COLLECTION)
            except Exception:
                pass
            collection = client.create_collection(
                name=CHROMA_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )
            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=[
                    {"id": c["id"], "title": c["title"], "category": c["category"]}
                    for c in POLICY_CLAUSES
                ],
            )
            print(f"[OK] Ingested {len(POLICY_CLAUSES)} clauses into ChromaDB.")
        except Exception as e:
            print(f"[WARN] ChromaDB write failed ({e}). TF-IDF store already saved.")
    else:
        print(f"[OK] TF-IDF store saved to {TFIDF_STORE_PATH}")

    # Write store metadata
    meta = {
        "backend": backend,
        "chroma_collection": CHROMA_COLLECTION,
        "tfidf_store_path": str(TFIDF_STORE_PATH),
        "clause_count": len(POLICY_CLAUSES),
        "clause_ids": ids,
    }
    METADATA_PATH.write_text(json.dumps(meta, indent=2))
    print(f"[OK] Metadata saved → {METADATA_PATH}")
    return meta


if __name__ == "__main__":
    result = ingest()
    print(f"\nStore ready. Backend: {result['backend']}")
    print(f"Clauses indexed: {result['clause_ids']}")
