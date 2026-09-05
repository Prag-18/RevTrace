"""
FastAPI layer for the RevTrace dashboard.

Serves everything the React frontend needs:
  GET  /batch/summary        -> batch_summary.json contents
  GET  /batch/events         -> list of all events with final status
  GET  /events/{event_id}/audit -> full audit trail for one event
  GET  /model/metrics        -> model training/evaluation metrics
  POST /batch/run            -> re-run the batch (for a live demo)
  POST /simulate             -> run a custom, user-defined event through
                                 the live pipeline (for a live "what if"
                                 demo — does NOT touch the real audit log)

Run:
    cd backend/api
    uvicorn main:app --reload --port 8000
"""

import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(BACKEND_DIR, "data")
MODELS_DIR = os.path.join(BACKEND_DIR, "models")

app = FastAPI(title="RevTrace API")

# Vite's default dev server port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_json(path: str) -> dict:
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"File not found: {os.path.basename(path)}. "
                                                      f"Have you run the corresponding script yet?")
    with open(path) as f:
        return json.load(f)


def _sanitize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Replace pandas NaN/NaT with None so the result is valid JSON.
    NaN legitimately appears here — e.g. 'outcome' is null for a step
    that got escalated rather than getting a customer response, and
    'block_reason' is null for any step that wasn't blocked.
    """
    return df.astype(object).where(pd.notnull(df), None)


@app.get("/")
def root():
    return {"status": "ok", "service": "RevTrace API"}


@app.get("/batch/summary")
def batch_summary():
    return _load_json(os.path.join(DATA_DIR, "batch_summary.json"))


@app.get("/batch/events")
def batch_events():
    """Return per-event outcomes by replaying the audit log's final row
    per event (works for both CSV and Supabase backends).
    """
    from audit import AuditLogger
    logger = AuditLogger()

    if logger.backend == "csv":
        df = logger.read_all()
    else:
        # Supabase: pull everything via the client directly
        response = logger.client.table("audit_log").select("*").execute()
        df = pd.DataFrame(response.data)

    if df.empty:
        return {"events": []}

    # one row per event: its LAST audit step (the terminal outcome)
    last_steps = df.sort_values("step_number").groupby("event_id").tail(1)

    cols = last_steps[[
        "event_id", "decline_code", "cause_category", "amount",
        "event_status_after", "attempt_count_before", "outcome",
    ]].rename(columns={"event_status_after": "final_status"})
    events = _sanitize_df(cols).to_dict(orient="records")

    return {"events": events}


@app.get("/events/{event_id}/audit")
def event_audit(event_id: str):
    from audit import AuditLogger
    logger = AuditLogger()

    if logger.backend == "csv":
        df = logger.read_all()
        if df.empty:
            raise HTTPException(status_code=404, detail="Audit log is empty. Run the batch first.")
        rows = df[df["event_id"] == event_id]
    else:
        response = logger.client.table("audit_log").select("*").eq("event_id", event_id).execute()
        rows = pd.DataFrame(response.data)

    if rows.empty:
        raise HTTPException(status_code=404, detail=f"No audit trail found for event_id '{event_id}'")

    rows = rows.sort_values("step_number")
    return {"event_id": event_id, "steps": _sanitize_df(rows).to_dict(orient="records")}


@app.get("/model/metrics")
def model_metrics():
    return _load_json(os.path.join(MODELS_DIR, "metrics.json"))


@app.post("/batch/run")
def run_batch_endpoint(n: int = None, live: bool = False):
    """Re-run the batch on demand — used for a live 'run it in front of
    judges' demo moment. Runs synchronously; for 180 events in mock mode
    this typically completes in a few seconds.
    """
    from run_batch import run_batch
    try:
        results_df, metrics = run_batch(n=n, live_razorpay=live, clear_audit_log=True)
        return {"status": "completed", "metrics": metrics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# /simulate — run a custom, user-defined event through the SAME live
# pipeline used by the real batch, for a live "what if" demo. This is
# intentionally kept separate from the real audit log: nothing here is
# written to CSV/Supabase, so a judge trying wild hypothetical scenarios
# can never corrupt or pad the real batch results.
# ---------------------------------------------------------------------------

VALID_DECLINE_CODES = [
    "insufficient_funds", "limit_exceeded", "card_expired", "invalid_cvv",
    "bank_technical_decline", "issuer_unavailable", "do_not_honor",
    "fraud_suspected_by_issuer",
]


class SimulateRequest(BaseModel):
    decline_code: str = Field(..., description="One of the known decline codes")
    amount: float = Field(..., gt=0)
    event_type: str = Field("payment_failure", description="payment_failure or subscription_renewal_failure")
    customer_tenure_days: int = Field(180, ge=0)
    customer_past_success_rate: float = Field(0.85, ge=0, le=1)
    customer_prior_failures_30d: int = Field(0, ge=0)
    is_first_time_customer: bool = False
    day_of_month: int = Field(15, ge=1, le=31)
    # None = don't simulate a customer outcome at all, just show the
    # decisions the agent would make at each step. True/False = simulate
    # as if this event genuinely would/wouldn't have recovered, using the
    # same friction model as the real batch backtest.
    assume_recoverable: Optional[bool] = None


def _serialize_step(step_result) -> dict:
    row = asdict(step_result)
    if isinstance(row.get("simulated_timestamp"), datetime):
        row["simulated_timestamp"] = row["simulated_timestamp"].isoformat()
    return row


@app.post("/simulate")
def simulate_event(req: SimulateRequest):
    if req.decline_code not in VALID_DECLINE_CODES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown decline_code '{req.decline_code}'. Valid options: {VALID_DECLINE_CODES}",
        )

    from state_machine import EventLifecycle
    from policy import PolicyEngine
    from executor import RazorpayExecutor
    import uuid

    event = {
        "event_id": f"sim_{uuid.uuid4().hex[:10]}",
        "decline_code": req.decline_code,
        "amount": req.amount,
        "event_type": req.event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "day_of_month": req.day_of_month,
        "customer_tenure_days": req.customer_tenure_days,
        "customer_past_success_rate": req.customer_past_success_rate,
        "customer_prior_failures_30d": req.customer_prior_failures_30d,
        "is_first_time_customer": req.is_first_time_customer,
        "customer_id": "sim_customer",
        # only meaningful when assume_recoverable is not None
        "ground_truth_recoverable": bool(req.assume_recoverable) if req.assume_recoverable is not None else False,
    }

    try:
        policy_engine = PolicyEngine()
        # respects RAZORPAY_MODE from .env, same as a real single event —
        # if you have live credentials configured, this generates a REAL
        # test-mode payment link for the hypothetical scenario, which is
        # a nice live-demo moment
        executor = RazorpayExecutor()
        lifecycle = EventLifecycle(
            event, policy_engine, executor,
            backtest_mode=(req.assume_recoverable is not None),
        )
        history = lifecycle.run_to_completion()
    except ValueError as e:
        # e.g. diagnosis.py raising on an unrecognized decline_code —
        # shouldn't happen given the validation above, but stay defensive
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "event_id": event["event_id"],
        "final_status": lifecycle.status.value,
        "steps": [_serialize_step(s) for s in history],
    }