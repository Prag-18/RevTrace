"""
Tests for the FastAPI backend (Day 6).

Run:
    cd backend/tests
    pytest test_api.py -v

Requires backend/data/batch_summary.json and backend/data/audit_log.csv
to exist (i.e. run_batch.py must have been run at least once).
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "api"))
from main import app  # noqa: E402

client = TestClient(app)


class TestRoot:
    def test_root_ok(self):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestBatchSummary:
    def test_summary_returns_expected_fields(self):
        r = client.get("/batch/summary")
        assert r.status_code == 200
        body = r.json()
        required = {
            "n_events", "total_revenue_at_risk", "total_revenue_recovered",
            "overall_recovery_rate", "by_cause_category", "status_counts",
        }
        assert required.issubset(body.keys())

    def test_summary_numbers_are_internally_consistent(self):
        body = client.get("/batch/summary").json()
        assert body["total_revenue_recovered"] <= body["total_revenue_at_risk"]
        assert 0 <= body["overall_recovery_rate"] <= 1


class TestBatchEvents:
    def test_events_list_is_non_empty(self):
        r = client.get("/batch/events")
        assert r.status_code == 200
        assert len(r.json()["events"]) > 0

    def test_events_have_required_fields(self):
        events = client.get("/batch/events").json()["events"]
        required = {"event_id", "decline_code", "cause_category", "amount", "final_status"}
        for e in events[:10]:
            assert required.issubset(e.keys())

    def test_events_response_is_valid_json_no_nan_leaks(self):
        # this is the exact bug we hit and fixed — regression guard
        import json
        r = client.get("/batch/events")
        # if NaN leaked through, this response wouldn't even be valid JSON
        json.loads(r.text)

    def test_final_status_values_are_known(self):
        events = client.get("/batch/events").json()["events"]
        known = {"recovered", "escalated", "closed_lost", "open"}
        for e in events:
            assert e["final_status"] in known


class TestEventAudit:
    def test_audit_trail_for_a_real_event(self):
        events = client.get("/batch/events").json()["events"]
        sample_id = events[0]["event_id"]
        r = client.get(f"/events/{sample_id}/audit")
        assert r.status_code == 200
        body = r.json()
        assert body["event_id"] == sample_id
        assert len(body["steps"]) >= 1

    def test_audit_steps_are_ordered_by_step_number(self):
        # Use attempt_count_before (already present in /batch/events) to
        # find a multi-step event directly, instead of calling
        # /events/{id}/audit once per event to go fishing for one — that
        # older approach made up to 180 live network calls against a real
        # Supabase backend in a single test, which is slow and flaky
        # (transient connection resets become likely at that volume).
        # This version makes exactly 2 network calls total.
        events = client.get("/batch/events").json()["events"]
        multi_step_candidates = [e for e in events if e["attempt_count_before"] > 0]
        if not multi_step_candidates:
            pytest.skip("no multi-step event found in this batch")

        multi_step_id = multi_step_candidates[0]["event_id"]
        steps = client.get(f"/events/{multi_step_id}/audit").json()["steps"]
        step_numbers = [s["step_number"] for s in steps]
        assert step_numbers == sorted(step_numbers)

    def test_unknown_event_id_returns_404(self):
        r = client.get("/events/definitely_not_a_real_event_id/audit")
        assert r.status_code == 404

    def test_escalated_event_shows_blocked_step(self):
        events = client.get("/batch/events").json()["events"]
        escalated = [e for e in events if e["final_status"] == "escalated"]
        if not escalated:
            pytest.skip("no escalated events in this batch")
        r = client.get(f"/events/{escalated[0]['event_id']}/audit")
        steps = r.json()["steps"]
        assert any(s["blocked"] for s in steps), \
            "an escalated event should have at least one blocked step in its audit trail"


class TestModelMetrics:
    def test_metrics_returns_expected_fields(self):
        r = client.get("/model/metrics")
        assert r.status_code == 200
        body = r.json()
        required = {"production_model", "gradient_boosting", "logistic_regression",
                    "feature_importance"}
        assert required.issubset(body.keys())

    def test_both_models_have_cv_auc(self):
        body = client.get("/model/metrics").json()
        for key in ("gradient_boosting", "logistic_regression"):
            assert "cv_auc_mean" in body[key]


class TestSimulate:
    def test_basic_simulation_returns_steps(self):
        r = client.post("/simulate", json={
            "decline_code": "insufficient_funds",
            "amount": 1500,
            "assume_recoverable": True,
        })
        assert r.status_code == 200
        body = r.json()
        assert body["event_id"].startswith("sim_")
        assert len(body["steps"]) >= 1
        assert body["final_status"] in ("recovered", "escalated", "closed_lost")

    def test_fraud_suspected_never_auto_acts_even_if_assumed_recoverable(self):
        # THE critical compliance-gate demo case: even telling the
        # simulator "assume this would recover" must not override the
        # never_auto_action gate for issuer_risk_flag causes.
        r = client.post("/simulate", json={
            "decline_code": "fraud_suspected_by_issuer",
            "amount": 5000,
            "assume_recoverable": True,
        })
        body = r.json()
        assert body["final_status"] == "escalated"
        assert len(body["steps"]) == 1
        assert body["steps"][0]["policy_action"] == "escalate_human"
        assert body["steps"][0]["blocked"] is True
        assert body["steps"][0]["razorpay_payment_link_id"] is None

    def test_do_not_honor_also_never_auto_acts(self):
        r = client.post("/simulate", json={
            "decline_code": "do_not_honor",
            "amount": 2000,
            "assume_recoverable": True,
        })
        body = r.json()
        assert body["final_status"] == "escalated"
        assert body["steps"][0]["blocked"] is True

    def test_expired_card_always_requests_update_never_bare_retry(self):
        r = client.post("/simulate", json={
            "decline_code": "card_expired",
            "amount": 999,
            "assume_recoverable": False,
        })
        body = r.json()
        for step in body["steps"]:
            if step["policy_action"] not in ("escalate_human", "hold", "hold_closed_lost"):
                assert step["policy_action"] == "request_card_update"

    def test_assume_recoverable_none_skips_outcome_simulation(self):
        r = client.post("/simulate", json={
            "decline_code": "card_expired",
            "amount": 500,
            "assume_recoverable": None,
        })
        body = r.json()
        for step in body["steps"]:
            assert step["outcome"] is None

    def test_never_exceeds_attempt_cap(self):
        r = client.post("/simulate", json={
            "decline_code": "invalid_cvv",
            "amount": 300,
            "assume_recoverable": False,
        })
        body = r.json()
        attempt_steps = [s for s in body["steps"] if not s["blocked"]]
        assert len(attempt_steps) <= 3

    def test_unknown_decline_code_returns_400(self):
        r = client.post("/simulate", json={
            "decline_code": "not_a_real_code",
            "amount": 100,
        })
        assert r.status_code == 400

    def test_invalid_amount_returns_422(self):
        r = client.post("/simulate", json={
            "decline_code": "insufficient_funds",
            "amount": -50,
        })
        assert r.status_code == 422

    def test_response_is_valid_json_no_nan_leaks(self):
        import json
        r = client.post("/simulate", json={
            "decline_code": "bank_technical_decline",
            "amount": 750,
            "assume_recoverable": None,
        })
        json.loads(r.text)

    def test_does_not_pollute_real_audit_log(self):
        # simulate events must never show up in the real batch/events list
        before = client.get("/batch/events").json()["events"]
        before_ids = {e["event_id"] for e in before}

        r = client.post("/simulate", json={"decline_code": "insufficient_funds", "amount": 100})
        sim_id = r.json()["event_id"]

        after = client.get("/batch/events").json()["events"]
        after_ids = {e["event_id"] for e in after}

        assert sim_id not in after_ids
        assert before_ids == after_ids