"""
Runs ONE event through the full pipeline:
    decline_code -> diagnose (cause) -> score (recovery probability)
    -> policy.decide (action) -> executor (Razorpay call)

This is the Day 3 deliverable: proof the four pieces built so far
(diagnosis, model, policy, executor) actually compose into one working
loop for a single event, before Day 5 runs it across the full batch.
"""

import json
import os
import sys

import joblib
import pandas as pd

sys.path.append(os.path.dirname(__file__))
from diagnosis import diagnose
from policy import PolicyEngine, AttemptState
from executor import RazorpayExecutor, synthetic_indian_mobile

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")


def load_model_bundle():
    model = joblib.load(os.path.join(MODELS_DIR, "recovery_model.joblib"))
    scaler = joblib.load(os.path.join(MODELS_DIR, "scaler.joblib"))
    with open(os.path.join(MODELS_DIR, "feature_columns.json")) as f:
        feature_columns = json.load(f)
    return model, scaler, feature_columns


def score_event(model, scaler, feature_columns, event: dict, cause_category: str) -> float:
    """Build the exact feature vector the model expects and predict."""
    payday_proximity = 1 if (event["day_of_month"] <= 5 or event["day_of_month"] >= 26) else 0

    row = {
        "customer_tenure_days": event["customer_tenure_days"],
        "customer_past_success_rate": event["customer_past_success_rate"],
        "customer_prior_failures_30d": event["customer_prior_failures_30d"],
        "amount": event["amount"],
        "payday_proximity": payday_proximity,
    }
    df_row = pd.DataFrame([row])

    for col in feature_columns:
        df_row[col] = 0
    cause_col = f"cause_category_{cause_category}"
    event_type_col = f"event_type_{event['event_type']}"
    first_time_col = f"is_first_time_customer_{int(event['is_first_time_customer'])}"
    for col in (cause_col, event_type_col, first_time_col):
        if col in df_row.columns:
            df_row[col] = 1

    X = pd.concat([df_row[["customer_tenure_days", "customer_past_success_rate",
                            "customer_prior_failures_30d", "amount", "payday_proximity"]],
                   df_row[feature_columns]], axis=1)
    X_scaled = scaler.transform(X)
    return float(model.predict_proba(X_scaled)[0, 1])


def process_one_event(event: dict, state: AttemptState = None) -> dict:
    """Full pipeline for a single event. Returns a structured result dict
    that is exactly what will become one audit-trail row.
    """
    state = state or AttemptState()

    # 1. DIAGNOSE
    cause_info = diagnose(event["decline_code"])

    # 2. SCORE
    model, scaler, feature_columns = load_model_bundle()
    recovery_probability = score_event(model, scaler, feature_columns, event, cause_info.cause_category)

    # 3. DECIDE (policy)
    policy_engine = PolicyEngine()
    decision = policy_engine.decide(
        cause_category=cause_info.cause_category,
        recovery_probability=recovery_probability,
        state=state,
        event_amount=event["amount"],
    )

    result = {
        "event_id": event["event_id"],
        "decline_code": event["decline_code"],
        "cause_category": cause_info.cause_category,
        "diagnosis_rationale": cause_info.rationale,
        "recovery_probability": round(recovery_probability, 4),
        "attempt_count_before": state.attempt_count,
        "policy_action": decision.action,
        "policy_rationale": decision.rationale,
        "blocked": decision.blocked,
        "block_reason": decision.block_reason,
    }

    # 4. EXECUTE (only if policy allows a customer-facing action)
    executable_actions = {"retry_immediate", "retry_delayed",
                           "request_card_update", "escalate_alternate_payment"}
    if decision.action in executable_actions:
        executor = RazorpayExecutor()
        exec_result = executor.create_payment_link(
            event_id=event["event_id"],
            amount_rupees=event["amount"],
            customer_name=event.get("customer_id", "customer"),
            customer_contact=synthetic_indian_mobile(event.get("customer_id", event["event_id"])),  # deterministic, avoids Razorpay's recurring-digit validation
            description=f"Payment recovery: {decision.action} ({cause_info.cause_category})",
            action_type=decision.action,
        )
        result["razorpay_success"] = exec_result.success
        result["razorpay_payment_link_id"] = exec_result.payment_link_id
        result["razorpay_payment_link_url"] = exec_result.payment_link_url
        result["razorpay_mock"] = exec_result.mock
    else:
        result["razorpay_success"] = None
        result["razorpay_payment_link_id"] = None
        result["razorpay_payment_link_url"] = None
        result["razorpay_mock"] = None

    return result


if __name__ == "__main__":
    events_path = os.path.join(os.path.dirname(__file__), "..", "data", "events.csv")
    df = pd.read_csv(events_path)

    # pick 3 representative events: one clean retry case, one expired card,
    # one risk-flag case, to demonstrate all three branches of the policy
    sample = pd.concat([
        df[df["decline_code"] == "insufficient_funds"].head(1),
        df[df["decline_code"] == "card_expired"].head(1),
        df[df["decline_code"] == "fraud_suspected_by_issuer"].head(1),
    ])

    for _, row in sample.iterrows():
        event = row.to_dict()
        result = process_one_event(event)
        print(f"\n{'='*70}")
        print(f"Event {result['event_id']}  |  decline_code={result['decline_code']}")
        print(f"  cause_category:       {result['cause_category']}")
        print(f"  recovery_probability: {result['recovery_probability']}")
        print(f"  policy_action:        {result['policy_action']}  (blocked={result['blocked']})")
        print(f"  rationale:            {result['policy_rationale']}")
        if result['razorpay_payment_link_url']:
            print(f"  razorpay_link:        {result['razorpay_payment_link_url']} "
                  f"(mock={result['razorpay_mock']})")