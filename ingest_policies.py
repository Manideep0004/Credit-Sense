"""
ingest_policies.py
------------------
Legacy entry point delegating to the modular rag.ingest pipeline.

Run:
    python ingest_policies.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rag.ingest import ingest_policy_corpus


def ingest(force_tfidf: bool = False):
    return ingest_policy_corpus(force_tfidf=force_tfidf)


if __name__ == "__main__":
    result = ingest()
    print(f"\nStore ready. Backend: {result['backend']}")
    print(f"Clauses indexed: {result['clause_ids']}")

