"""
policy_corpus.py
----------------
Hardcoded lending-policy / KYC-AML clause corpus.

Each clause is a dict with:
  - id       : unique clause reference (e.g. "DTI-1.1")
  - title    : short human-readable title
  - text     : full clause text (used for embedding / retrieval)
  - category : logical grouping

Import POLICY_CLAUSES from this module wherever the corpus is needed.
"""

POLICY_CLAUSES = [
    {
        "id": "DTI-1.1",
        "title": "Maximum Debt-to-Income Ratio",
        "category": "Credit Risk",
        "text": (
            "DTI-1.1 — Debt-to-Income (DTI) Threshold: "
            "No loan shall be approved where the applicant's total existing monthly "
            "debt obligations exceed 55% of their gross monthly income (DTI ratio > 0.55). "
            "Applicants with DTI between 0.45 and 0.55 require senior underwriter sign-off. "
            "DTI is computed as: existing_monthly_debt / monthly_income."
        ),
    },
    {
        "id": "DTI-1.2",
        "title": "First-Time Borrower Income Limit",
        "category": "Credit Risk",
        "text": (
            "DTI-1.2 — First-Time Borrower Limits: "
            "Applicants with zero prior credit history (past_defaults = 0 AND no prior loans) "
            "are eligible for a maximum loan amount of 12× their monthly income. "
            "The requested loan amount must not exceed this ceiling. "
            "Applications exceeding this limit must be referred to the credit committee."
        ),
    },
    {
        "id": "DEFAULT-2.1",
        "title": "Repeat Defaulter Policy",
        "category": "Credit History",
        "text": (
            "DEFAULT-2.1 — Repeat Defaulter Exclusion: "
            "Applicants with more than one recorded prior loan default (past_defaults > 1) "
            "are classified as repeat defaulters and must be escalated to manual review. "
            "Automatic approval is prohibited regardless of current risk score or income level. "
            "A cooling-off period of 36 months from the date of last settlement applies."
        ),
    },
    {
        "id": "DEFAULT-2.2",
        "title": "Single Default Disclosure",
        "category": "Credit History",
        "text": (
            "DEFAULT-2.2 — Single Prior Default: "
            "Applicants with exactly one prior default may be considered for approval "
            "provided the DTI ratio is below 0.40, credit utilisation is below 50%, "
            "and employment tenure exceeds 3 years. Such cases require documented "
            "underwriter commentary explaining the mitigating factors."
        ),
    },
    {
        "id": "AML-3.1",
        "title": "AML Structuring Risk",
        "category": "AML / CFT",
        "text": (
            "AML-3.1 — Structuring and Unusual Transaction Patterns: "
            "Where an applicant's transaction volatility score exceeds 80 (scale 0-100) "
            "AND the requested loan amount is more than 10 times their monthly income, "
            "the application is flagged for AML structuring risk. "
            "Such applications must be escalated to the AML Compliance Cell and cannot "
            "be auto-approved. A Suspicious Transaction Report (STR) must be considered "
            "in line with PMLA 2002 obligations."
        ),
    },
    {
        "id": "KYC-4.1",
        "title": "KYC Completeness Requirement",
        "category": "KYC / Identity",
        "text": (
            "KYC-4.1 — Mandatory KYC Verification: "
            "No loan disbursement may proceed unless the applicant's KYC documents have "
            "been fully verified in accordance with RBI Master Direction on KYC (2016, "
            "updated 2023). Incomplete KYC (kyc_verified = 0) is a hard block; "
            "the application must be placed on hold until documents are received and "
            "verified. Auto-approval is strictly prohibited for KYC-incomplete cases."
        ),
    },
    {
        "id": "KYC-4.2",
        "title": "PEP and Sanctions Screening",
        "category": "KYC / Identity",
        "text": (
            "KYC-4.2 — Politically Exposed Persons (PEP) and Sanctions Screening: "
            "All applicants must be screened against the UN Consolidated Sanctions List, "
            "OFAC SDN list, and the domestic PEP database prior to approval. "
            "Any positive match results in an immediate escalation to the compliance officer "
            "and suspension of the application pending further due diligence. "
            "This screening must be documented in the loan file."
        ),
    },
    {
        "id": "RISK-5.1",
        "title": "High Risk Tier Referral",
        "category": "Risk Tiering",
        "text": (
            "RISK-5.1 — High and Severe Risk Tier Handling: "
            "Applications where the ML-based risk model assigns a default probability "
            "above 0.60 (SEVERE tier) must be referred to manual review regardless of "
            "other indicators. Applications with default probability between 0.40 and 0.60 "
            "(HIGH tier) require senior underwriter approval with documented risk acceptance. "
            "LOW tier (< 0.20) and MODERATE tier (0.20-0.40) may proceed to auto-decision "
            "subject to compliance clearance."
        ),
    },
]


def get_clause_by_id(clause_id: str) -> dict | None:
    """Return a policy clause dict by its ID, or None if not found."""
    for clause in POLICY_CLAUSES:
        if clause["id"] == clause_id:
            return clause
    return None


def get_all_texts() -> list[str]:
    """Return the full text of every clause (for embedding / indexing)."""
    return [c["text"] for c in POLICY_CLAUSES]


def get_all_ids() -> list[str]:
    """Return all clause IDs in corpus order."""
    return [c["id"] for c in POLICY_CLAUSES]


if __name__ == "__main__":
    print(f"Policy corpus: {len(POLICY_CLAUSES)} clauses\n")
    for c in POLICY_CLAUSES:
        print(f"  [{c['id']}] {c['title']}  ({c['category']})")
