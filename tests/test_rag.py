"""
creditsense/tests/test_rag.py
-----------------------------
Unit and integration tests for RAG policy corpus, ingestion pipeline, metadata, and retrievers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure creditsense package root is on path
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.corpus import POLICY_CLAUSES, get_all_clauses, get_clause_by_id
from rag.ingest import ingest_policy_corpus
from rag.vectorstore import BaseRetriever, TfidfRetriever, get_retriever


def test_policy_corpus_metadata():
    """Verify that all policy clauses contain the mandatory metadata fields."""
    clauses = get_all_clauses()
    assert len(clauses) >= 8

    required_keys = {
        "id",
        "title",
        "category",
        "document",
        "section",
        "policy_type",
        "version",
        "source",
        "text",
    }

    for c in clauses:
        for k in required_keys:
            assert k in c, f"Clause {c.get('id')} missing required key '{k}'"
            assert isinstance(c[k], str) and len(c[k]) > 0


def test_get_clause_by_id():
    """Test lookup helper by ID."""
    c = get_clause_by_id("AML-3.1")
    assert c is not None
    assert c["title"] == "AML Structuring Risk"
    assert "PMLA 2002" in c["text"]

    none_c = get_clause_by_id("NON_EXISTENT_ID")
    assert none_c is None


def test_tfidf_ingestion_and_retrieval():
    """Test ingestion and semantic search using TF-IDF sparse retriever."""
    meta = ingest_policy_corpus(force_tfidf=True)
    assert meta["clause_count"] == len(POLICY_CLAUSES)
    assert meta["backend"] == "tfidf-sklearn"

    retriever = TfidfRetriever()
    assert isinstance(retriever, BaseRetriever)

    # 1. Query AML structuring
    aml_results = retriever.retrieve(
        "high transaction volatility score suspicious AML structuring",
        top_k=2,
    )
    assert len(aml_results) > 0
    top_id = aml_results[0]["id"]
    assert top_id == "AML-3.1"
    assert aml_results[0]["document"] == "Anti_Money_Laundering_and_CFT_Manual.pdf"

    # 2. Query KYC verification
    kyc_results = retriever.retrieve(
        "missing KYC identity verification unverified documents",
        top_k=2,
    )
    assert len(kyc_results) > 0
    assert any(c["id"] == "KYC-4.1" for c in kyc_results)

    # 3. Query DTI
    dti_results = retriever.retrieve(
        "maximum debt to income ratio 55 percent threshold",
        top_k=2,
    )
    assert len(dti_results) > 0
    assert any(c["id"] == "DTI-1.1" for c in dti_results)


def test_retriever_factory():
    """Test get_retriever factory returns working instance with top-k output."""
    retriever = get_retriever()
    assert isinstance(retriever, BaseRetriever)
    results = retriever.retrieve("debt to income", top_k=2)
    assert len(results) <= 2
    assert len(results) > 0
    assert "id" in results[0]
    assert "text" in results[0]
    assert "score" in results[0]
