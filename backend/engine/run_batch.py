"""
Day 5: Full batch run.

Processes every event in data/events.csv through the complete pipeline
(diagnose -> score -> decide -> execute -> simulate outcome -> repeat
until terminal), writes every step to the audit trail, and computes the
batch-level business metrics that are the actual deliverable for this
track's bar: measured money recovered, with escalation and stopping
rules visible in the numbers, not just described.

By default, Razorpay calls run in MOCK mode regardless of RAZORPAY_MODE
in .env — running the full batch (180 events x up to 3 attempts) could
mean 400+ live API calls, which isn't necessary since Day 3 already
proved the live integration works end-to-end. Pass --live to use real
Razorpay test-mode calls for the whole batch instead.

The audit trail backend (CSV vs Supabase) is controlled by AUDIT_BACKEND
in .env, independent of the Razorpay mode — so you can log to real
Supabase while still using mock payment links, which is the recommended
setup for a full-batch run.

Run:
    python run_batch.py
    python run_batch.py --live          # real Razorpay calls too
    python run_batch.py --n 50          # smaller batch for a quick check
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "engine"))
from state_machine import EventLifecycle, EventStatus  # noqa: E402
from policy import PolicyEngine  # noqa: E402
from executor import RazorpayExecutor  # noqa: E402
from audit import AuditLogger  # noqa: E402

# This module lives in ``backend/engine`` while generated data is stored in
# ``backend/data``.  Build both paths from the module location so the command
# works regardless of the shell's current directory.
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BACKEND_DIR, "data", "events.csv")
SUMMARY_PATH = os.path.join(BACKEND_DIR, "data", "batch_summary.json")


def run_batch(n: int = None, live_razorpay: bool = False, clear_audit_log: bool = True,
              random_seed: int = 42):
    import random
    rng = random.Random(random_seed)

    df = pd.read_csv(DATA_PATH)
    if n is not None:
        df = df.head(n)

    policy_engine = PolicyEngine()
    executor = RazorpayExecutor(mock=not live_razorpay)
    audit_logger = AuditLogger()

    print(f"Running batch of {len(df)} events")
    print(f"  Razorpay mode:  {'LIVE' if live_razorpay else 'MOCK'}")
    print(f"  Audit backend:  {audit_logger.backend}")

    if clear_audit_log:
        audit_logger.clear()
        print(f"  Cleared previous audit log.\n")

    event_results = []
    total_audit_rows = 0

    for i, (_, row) in enumerate(df.iterrows()):
        event = row.to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor, rng=rng)
        history = lifecycle.run_to_completion()

        audit_logger.log_steps(history)
        total_audit_rows += len(history)

        event_results.append({
            "event_id": event["event_id"],
            "decline_code": event["decline_code"],
            "cause_category": lifecycle.cause_info.cause_category,
            "amount": event["amount"],
            "final_status": lifecycle.status.value,
            "attempts_used": lifecycle.state.attempt_count,
            "steps_taken": len(history),
            "ground_truth_recoverable": bool(event["ground_truth_recoverable"]),
            "recovered": lifecycle.status == EventStatus.RECOVERED,
        })

        if (i + 1) % 30 == 0 or (i + 1) == len(df):
            print(f"  processed {i + 1}/{len(df)} events...")

    print(f"\nWrote {total_audit_rows} audit rows across {len(event_results)} events.\n")

    results_df = pd.DataFrame(event_results)
    metrics = compute_metrics(results_df)
    print_metrics(metrics)

    with open(SUMMARY_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved batch summary -> {SUMMARY_PATH}")

    return results_df, metrics


def compute_metrics(results_df: pd.DataFrame) -> dict:
    total_at_risk = float(results_df["amount"].sum())
    total_recovered = float(results_df.loc[results_df["recovered"], "amount"].sum())

    baseline_recoverable = float(
        results_df.loc[results_df["ground_truth_recoverable"], "amount"].sum()
    )
    # revenue the agent actually captured, as a share of what was ever
    # recoverable in the first place (a fairer "how good is the agent"
    # number than raw ₹ recovered / total at risk, since some events were
    # never going to recover no matter what anyone did)
    capture_rate_of_recoverable = (
        total_recovered / baseline_recoverable if baseline_recoverable > 0 else 0.0
    )

    status_counts = results_df["final_status"].value_counts().to_dict()

    by_cause = results_df.groupby("cause_category").agg(
        n_events=("event_id", "count"),
        amount_at_risk=("amount", "sum"),
        amount_recovered=("amount", lambda s: results_df.loc[s.index].loc[
            results_df.loc[s.index, "recovered"], "amount"].sum()),
        recovery_rate=("recovered", "mean"),
    ).round(2).to_dict(orient="index")

    avg_attempts_to_terminal = float(results_df["attempts_used"].mean())
    escalated_count = int((results_df["final_status"] == "escalated").sum())
    closed_lost_count = int((results_df["final_status"] == "closed_lost").sum())
    recovered_count = int((results_df["final_status"] == "recovered").sum())

    return {
        "n_events": int(len(results_df)),
        "total_revenue_at_risk": round(total_at_risk, 2),
        "total_revenue_recovered": round(total_recovered, 2),
        "overall_recovery_rate": round(total_recovered / total_at_risk, 4) if total_at_risk else 0,
        "baseline_recoverable_revenue_no_intervention": round(baseline_recoverable, 2),
        "capture_rate_of_recoverable_revenue": round(capture_rate_of_recoverable, 4),
        "status_counts": {k: int(v) for k, v in status_counts.items()},
        "recovered_count": recovered_count,
        "escalated_count": escalated_count,
        "closed_lost_count": closed_lost_count,
        "avg_attempts_per_event": round(avg_attempts_to_terminal, 2),
        "by_cause_category": by_cause,
    }


def print_metrics(m: dict):
    print("=" * 70)
    print("BATCH RESULTS")
    print("=" * 70)
    print(f"Events processed:               {m['n_events']}")
    print(f"Total revenue at risk:           Rs {m['total_revenue_at_risk']:,.2f}")
    print(f"Total revenue recovered:         Rs {m['total_revenue_recovered']:,.2f}")
    print(f"Overall recovery rate:           {m['overall_recovery_rate']:.1%}")
    print(f"Baseline recoverable (no-op):     Rs {m['baseline_recoverable_revenue_no_intervention']:,.2f}")
    print(f"Capture rate of recoverable rev:  {m['capture_rate_of_recoverable_revenue']:.1%}")
    print()
    print(f"Recovered: {m['recovered_count']}   Escalated: {m['escalated_count']}   "
          f"Closed lost: {m['closed_lost_count']}")
    print(f"Avg attempts per event:          {m['avg_attempts_per_event']}")
    print()
    print("By cause category:")
    for cause, stats in m["by_cause_category"].items():
        print(f"  {cause:22s} n={stats['n_events']:3d}  "
              f"at_risk=Rs{stats['amount_at_risk']:>10,.0f}  "
              f"recovered=Rs{stats['amount_recovered']:>10,.0f}  "
              f"rate={stats['recovery_rate']:.1%}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=None, help="limit to first N events")
    parser.add_argument("--live", action="store_true", help="use real Razorpay test-mode API calls")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-clear", action="store_true", help="don't clear the audit log first")
    args = parser.parse_args()

    run_batch(n=args.n, live_razorpay=args.live, clear_audit_log=not args.no_clear,
              random_seed=args.seed)
