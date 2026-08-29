"""
Synthetic data generator for the AI Revenue Recovery pipeline.

Generates a batch of failed payment / failed subscription-renewal events with:
  - realistic decline-code distribution
  - customer history features
  - a HIDDEN ground truth (recoverable? which action would have worked?)
    used later for model training/evaluation and for the final
    business-impact metric ("recovered vs. would-have-been-lost").

Run:
    python generate_events.py --n 180 --seed 42 --out ../data/events.csv
"""

import argparse
import random
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 1. Decline-code taxonomy
# ---------------------------------------------------------------------------
# Each code maps to a cause_category (used by the rules-based diagnosis engine)
# and carries a *base* recovery probability + noise profile used to build the
# hidden ground truth label. These numbers are loosely inspired by published
# card-decline recovery benchmarks (Stripe/industry dunning reports) — not
# exact, but directionally realistic.

DECLINE_CODES = {
    "insufficient_funds":        {"cause": "insufficient_funds",   "weight": 0.28, "base_recovery": 0.45},
    "card_expired":               {"cause": "expired_card",         "weight": 0.20, "base_recovery": 0.15},
    "invalid_cvv":                 {"cause": "data_entry_error",     "weight": 0.10, "base_recovery": 0.20},
    "bank_technical_decline":      {"cause": "issuer_technical",     "weight": 0.14, "base_recovery": 0.80},
    "issuer_unavailable":          {"cause": "issuer_technical",     "weight": 0.08, "base_recovery": 0.75},
    "do_not_honor":                 {"cause": "issuer_risk_flag",     "weight": 0.10, "base_recovery": 0.15},
    "limit_exceeded":               {"cause": "insufficient_funds",   "weight": 0.06, "base_recovery": 0.40},
    "fraud_suspected_by_issuer":     {"cause": "issuer_risk_flag",     "weight": 0.04, "base_recovery": 0.05},
}

# The action that *actually* works best per cause, used to build the hidden
# ground-truth "best action" label (not shown to the diagnosis/policy engine).
BEST_ACTION_BY_CAUSE = {
    "insufficient_funds": "retry_delayed",
    "expired_card":        "request_card_update",
    "data_entry_error":    "request_card_update",
    "issuer_technical":    "retry_immediate",
    "issuer_risk_flag":    "escalate_alternate_payment",
}

EVENT_TYPES = ["payment_failure", "subscription_renewal_failure"]

# ---------------------------------------------------------------------------
# 2. Helpers
# ---------------------------------------------------------------------------

def sample_decline_code(rng):
    codes = list(DECLINE_CODES.keys())
    weights = [DECLINE_CODES[c]["weight"] for c in codes]
    return rng.choices(codes, weights=weights, k=1)[0]


def sample_customer_profile(rng):
    """Generate a customer history profile. Some customers are 'shaky'
    payers (low success rate, frequent recent failures), most are reliable.
    """
    is_shaky = rng.random() < 0.22
    if is_shaky:
        tenure = rng.randint(5, 400)
        past_success_rate = round(rng.uniform(0.35, 0.70), 2)
        prior_failures_30d = rng.randint(1, 4)
    else:
        tenure = rng.randint(30, 1800)
        past_success_rate = round(rng.uniform(0.75, 0.99), 2)
        prior_failures_30d = rng.choices([0, 1], weights=[0.85, 0.15])[0]

    is_first_time = tenure < 14
    return tenure, past_success_rate, prior_failures_30d, is_first_time


def compute_ground_truth_recovery_prob(decline_code, tenure, past_success_rate,
                                        prior_failures_30d, is_first_time,
                                        day_of_month, event_type):
    """
    Build a recovery probability from INTERACTING features (not a pure
    lookup), so the pattern is genuinely learnable but not trivial —
    this is what justifies using an ML model rather than a flat rules table.
    """
    base = DECLINE_CODES[decline_code]["base_recovery"]
    cause = DECLINE_CODES[decline_code]["cause"]

    p = base

    # Reliable customers recover more often across the board (they tend to
    # fix issues / have backup funds), especially for insufficient_funds.
    if cause == "insufficient_funds":
        p += (past_success_rate - 0.7) * 0.5          # scales with reliability
        # payday proximity: funds more likely available in first 5 days
        # or last 5 days of month (common salary-credit windows in India)
        if day_of_month <= 5 or day_of_month >= 26:
            p += 0.15

    # Repeated recent failures make any cause harder to recover (customer
    # may be actively disengaging, card genuinely broken, etc.)
    p -= prior_failures_30d * 0.08

    # Long-tenure customers are generally easier to win back (more trust,
    # more likely to update a card proactively) except for hard technical
    # failures where tenure doesn't matter much.
    if cause in ("expired_card", "data_entry_error"):
        p += min(tenure / 3000, 0.15)

    # First-time customers with a failure are the hardest to recover —
    # no relationship/trust built yet.
    if is_first_time:
        p -= 0.15

    # Subscription renewals recover slightly better than one-off payments
    # (existing relationship, auto-retry expectation already set).
    if event_type == "subscription_renewal_failure":
        p += 0.05

    # small irreducible noise so the problem isn't perfectly deterministic
    p += np.random.normal(0, 0.06)

    return float(np.clip(p, 0.02, 0.97))


# ---------------------------------------------------------------------------
# 3. Main generation loop
# ---------------------------------------------------------------------------

def generate_events(n: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    np.random.seed(seed)

    rows = []
    # Pool of repeat customers (~35% of events come from customers who
    # appear more than once, to mimic real repeat-failure patterns)
    n_unique_customers = int(n * 0.75)
    customer_pool = [f"cust_{i:04d}" for i in range(n_unique_customers)]

    start_date = datetime(2026, 6, 1)

    for _ in range(n):
        customer_id = rng.choice(customer_pool)
        tenure, past_success_rate, prior_failures_30d, is_first_time = sample_customer_profile(rng)

        event_type = rng.choices(EVENT_TYPES, weights=[0.6, 0.4], k=1)[0]
        decline_code = sample_decline_code(rng)
        cause = DECLINE_CODES[decline_code]["cause"]

        days_offset = rng.randint(0, 89)
        ts = start_date + timedelta(days=days_offset, hours=rng.randint(0, 23))
        day_of_month = ts.day

        # amount: subscription renewals cluster around plan price points,
        # one-off payments are more spread out
        if event_type == "subscription_renewal_failure":
            amount = round(rng.choice([299, 499, 999, 1499, 2499]) * rng.uniform(0.95, 1.0), 2)
        else:
            amount = round(np.random.lognormal(mean=6.5, sigma=0.9), 2)
            amount = float(min(max(amount, 150), 25000))

        recovery_prob = compute_ground_truth_recovery_prob(
            decline_code, tenure, past_success_rate, prior_failures_30d,
            is_first_time, day_of_month, event_type
        )
        ground_truth_recoverable = np.random.random() < recovery_prob

        rows.append({
            "event_id": f"evt_{uuid.uuid4().hex[:10]}",
            "customer_id": customer_id,
            "event_type": event_type,
            "amount": amount,
            "decline_code": decline_code,
            "timestamp": ts.isoformat(),
            "day_of_month": day_of_month,
            "customer_tenure_days": tenure,
            "customer_past_success_rate": past_success_rate,
            "customer_prior_failures_30d": prior_failures_30d,
            "is_first_time_customer": is_first_time,
            # --- hidden ground truth (answer key — not for the live engine) ---
            "ground_truth_recovery_prob": round(recovery_prob, 4),
            "ground_truth_recoverable": bool(ground_truth_recoverable),
            "ground_truth_best_action": BEST_ACTION_BY_CAUSE[cause],
        })

    df = pd.DataFrame(rows)
    return df


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic revenue-recovery events")
    parser.add_argument("--n", type=int, default=180, help="number of events to generate")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument("--out", type=str, default="../data/events.csv", help="output CSV path")
    args = parser.parse_args()

    df = generate_events(args.n, args.seed)
    df.to_csv(args.out, index=False)

    # ---- sanity check summary printed to console ----
    print(f"Generated {len(df)} events -> {args.out}\n")

    print("Decline code distribution:")
    print(df["decline_code"].value_counts(normalize=True).round(3), "\n")

    print("Recovery rate by decline_code (ground truth):")
    print(df.groupby("decline_code")["ground_truth_recoverable"].mean().round(3), "\n")

    print("Recovery rate by event_type:")
    print(df.groupby("event_type")["ground_truth_recoverable"].mean().round(3), "\n")

    total_at_risk = df["amount"].sum()
    total_recoverable = df.loc[df["ground_truth_recoverable"], "amount"].sum()
    print(f"Total revenue at risk: {total_at_risk:,.2f}")
    print(f"Ground-truth recoverable revenue (upper bound, no intervention cost): "
          f"{total_recoverable:,.2f} ({total_recoverable/total_at_risk:.1%})")


if __name__ == "__main__":
    main()