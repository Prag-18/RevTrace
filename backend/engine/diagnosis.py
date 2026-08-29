"""
Diagnosis engine — deterministic, rules-based.

Maps a raw decline_code (the signal we actually get from the payment
gateway) to a cause_category (the thing that determines the right
intervention). This is intentionally NOT machine-learned: decline codes
are already an unambiguous structured signal from the bank/issuer, so a
lookup table is more defensible and more explainable than a model here.

The ML layer (scoring.py) sits ON TOP of this, predicting *how likely*
a given cause is to recover given customer context — that's the genuinely
uncertain part worth learning.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CauseInfo:
    cause_category: str
    description: str
    # Human-readable rationale — shown in the audit trail so every
    # diagnosis is explainable, not a black box.
    rationale: str


# decline_code -> CauseInfo
DECLINE_CODE_TO_CAUSE = {
    "insufficient_funds": CauseInfo(
        cause_category="insufficient_funds",
        description="Card had insufficient funds at time of charge",
        rationale="Issuer reported insufficient funds; likely to resolve if retried near a probable pay date.",
    ),
    "limit_exceeded": CauseInfo(
        cause_category="insufficient_funds",
        description="Card credit/spend limit exceeded",
        rationale="Issuer reported limit exceeded; treated as an insufficient-funds variant — may resolve on delayed retry.",
    ),
    "card_expired": CauseInfo(
        cause_category="expired_card",
        description="Card on file has expired",
        rationale="Card is expired; retrying the same card cannot succeed. Requires the customer to provide updated card details.",
    ),
    "invalid_cvv": CauseInfo(
        cause_category="data_entry_error",
        description="CVV mismatch or invalid",
        rationale="Likely a stale or mistyped CVV on file; requires the customer to re-enter payment details.",
    ),
    "bank_technical_decline": CauseInfo(
        cause_category="issuer_technical",
        description="Generic technical decline from issuing bank",
        rationale="Non-specific technical failure at the issuer; a high proportion of these succeed on immediate retry.",
    ),
    "issuer_unavailable": CauseInfo(
        cause_category="issuer_technical",
        description="Issuing bank system temporarily unavailable",
        rationale="Issuer system was unreachable; retrying after a short delay commonly succeeds.",
    ),
    "do_not_honor": CauseInfo(
        cause_category="issuer_risk_flag",
        description="Issuer declined with a generic risk-based 'do not honor'",
        rationale="Issuer applied a risk-based decline; aggressive retry can worsen standing with the issuer. Prefer an alternate payment method.",
    ),
    "fraud_suspected_by_issuer": CauseInfo(
        cause_category="issuer_risk_flag",
        description="Issuer flagged the transaction as potentially fraudulent",
        rationale="Issuer suspects fraud; retrying is inappropriate and may trigger further risk flags. Escalate to alternate verified payment method only.",
    ),
}


def diagnose(decline_code: str) -> CauseInfo:
    """Return the CauseInfo for a given decline_code.

    Raises a clear error for unknown codes rather than silently guessing —
    an unrecognized decline code should be routed to human review, not
    auto-processed.
    """
    if decline_code not in DECLINE_CODE_TO_CAUSE:
        raise ValueError(
            f"Unknown decline_code '{decline_code}'. "
            f"This event should be routed to manual review, not auto-diagnosed."
        )
    return DECLINE_CODE_TO_CAUSE[decline_code]


if __name__ == "__main__":
    # quick self-check
    for code, info in DECLINE_CODE_TO_CAUSE.items():
        print(f"{code:30s} -> {info.cause_category:20s} | {info.description}")