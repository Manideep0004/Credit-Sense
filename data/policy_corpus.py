"""
data/policy_corpus.py
---------------------
Canonical policy clauses with backward compatibility aliases.
"""

from rag.corpus import (
    POLICY_CLAUSES,
    get_all_clauses,
    get_clause_by_id,
)


def get_all_texts() -> list[str]:
    return [c["text"] for c in POLICY_CLAUSES]


def get_all_ids() -> list[str]:
    return [c["id"] for c in POLICY_CLAUSES]


if __name__ == "__main__":
    print(f"Policy corpus: {len(POLICY_CLAUSES)} clauses\n")
    for c in POLICY_CLAUSES:
        print(f"  [{c['id']}] {c['title']}  ({c['category']})")
