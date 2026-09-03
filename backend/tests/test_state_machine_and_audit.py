"""
Tests for the event lifecycle state machine and audit logger (Day 4).

Run:
    cd backend/tests
    pytest test_state_machine_and_audit.py -v
"""

import os
import sys
from datetime import datetime, timezone

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engine"))
from state_machine import EventLifecycle, EventStatus  # noqa: E402
from policy import PolicyEngine  # noqa: E402
from executor import RazorpayExecutor  # noqa: E402
from audit import AuditLogger  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "events.csv")
TEST_CSV_PATH = os.path.join(os.path.dirname(__file__), "_test_audit_log.csv")


@pytest.fixture(autouse=True)
def force_mock_razorpay(monkeypatch):
    """Forces mock mode for every test in this file, regardless of a
    developer's local .env (see identical fixture in
    test_policy_and_executor.py for the full rationale)."""
    monkeypatch.setenv("RAZORPAY_MODE", "mock")


@pytest.fixture(scope="module")
def events_df():
    return pd.read_csv(DATA_PATH)


@pytest.fixture
def policy_engine():
    return PolicyEngine()


@pytest.fixture
def executor():
    return RazorpayExecutor(mock=True)  # force mock mode so tests never depend on local .env


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class TestEventLifecycle:
    def test_fraud_event_escalates_on_first_step_zero_attempts(self, events_df, policy_engine, executor):
        rows = events_df[events_df["decline_code"] == "fraud_suspected_by_issuer"]
        if len(rows) == 0:
            pytest.skip("no fraud events in batch")
        event = rows.iloc[0].to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        history = lifecycle.run_to_completion()

        assert lifecycle.status == EventStatus.ESCALATED
        assert len(history) == 1
        assert history[0].policy_action == "escalate_human"
        assert history[0].razorpay_payment_link_id is None

    def test_expired_card_event_eventually_terminates(self, events_df, policy_engine, executor):
        rows = events_df[events_df["decline_code"] == "card_expired"]
        if len(rows) == 0:
            pytest.skip("no card_expired events in batch")
        event = rows.iloc[0].to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        history = lifecycle.run_to_completion()

        # must reach a terminal state, never loop forever
        assert lifecycle.status in (EventStatus.RECOVERED, EventStatus.ESCALATED, EventStatus.CLOSED_LOST)
        assert len(history) <= EventLifecycle.MAX_STEPS

    def test_attempt_count_never_exceeds_policy_cap(self, events_df, policy_engine, executor):
        # global_limits.max_attempts_per_event is 3 in policy.yaml
        for decline_code in ["insufficient_funds", "card_expired", "data_entry_error"]:
            rows = events_df[events_df["decline_code"] == decline_code]
            if len(rows) == 0:
                continue
            event = rows.iloc[0].to_dict()
            lifecycle = EventLifecycle(event, policy_engine, executor)
            lifecycle.run_to_completion()
            assert lifecycle.state.attempt_count <= 3, (
                f"{decline_code} exceeded max_attempts_per_event: "
                f"{lifecycle.state.attempt_count}"
            )

    def test_recovered_event_stops_taking_further_action(self, events_df, policy_engine, executor):
        import random
        rows = events_df[events_df["decline_code"] == "bank_technical_decline"]
        if len(rows) == 0:
            pytest.skip("no bank_technical_decline events in batch")
        event = rows.iloc[0].to_dict()
        rng = random.Random(1)
        lifecycle = EventLifecycle(event, policy_engine, executor, rng=rng)
        history = lifecycle.run_to_completion()
        if lifecycle.status == EventStatus.RECOVERED:
            # once recovered, run_to_completion must have stopped immediately
            assert history[-1].outcome == "paid"

    def test_simulated_clock_advances_monotonically(self, events_df, policy_engine, executor):
        rows = events_df[events_df["decline_code"] == "card_expired"]
        if len(rows) == 0:
            pytest.skip("no card_expired events in batch")
        event = rows.iloc[0].to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        history = lifecycle.run_to_completion()
        timestamps = [r.simulated_timestamp for r in history]
        assert timestamps == sorted(timestamps), "simulated timestamps must be non-decreasing across steps"

    def test_never_exceeds_max_steps_safety_valve(self, events_df, policy_engine, executor):
        for _, row in events_df.head(15).iterrows():
            event = row.to_dict()
            lifecycle = EventLifecycle(event, policy_engine, executor)
            history = lifecycle.run_to_completion()
            assert len(history) <= EventLifecycle.MAX_STEPS


# ---------------------------------------------------------------------------
# Audit logger (CSV backend)
# ---------------------------------------------------------------------------

class TestAuditLoggerCSV:
    @pytest.fixture(autouse=True)
    def cleanup(self):
        if os.path.exists(TEST_CSV_PATH):
            os.remove(TEST_CSV_PATH)
        yield
        if os.path.exists(TEST_CSV_PATH):
            os.remove(TEST_CSV_PATH)

    def test_defaults_to_csv_backend(self):
        logger = AuditLogger(backend="csv", csv_path=TEST_CSV_PATH)
        assert logger.backend == "csv"

    def test_log_step_writes_a_row(self, events_df, policy_engine, executor):
        event = events_df.iloc[0].to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        history = lifecycle.run_to_completion()

        logger = AuditLogger(backend="csv", csv_path=TEST_CSV_PATH)
        logger.log_steps(history)

        result_df = logger.read_all()
        assert len(result_df) == len(history)

    def test_appends_across_multiple_events_not_overwrites(self, events_df, policy_engine, executor):
        logger = AuditLogger(backend="csv", csv_path=TEST_CSV_PATH)

        total_steps = 0
        for _, row in events_df.head(3).iterrows():
            event = row.to_dict()
            lifecycle = EventLifecycle(event, policy_engine, executor)
            history = lifecycle.run_to_completion()
            logger.log_steps(history)
            total_steps += len(history)

        result_df = logger.read_all()
        assert len(result_df) == total_steps
        assert result_df["event_id"].nunique() == 3

    def test_clear_removes_all_rows(self, events_df, policy_engine, executor):
        logger = AuditLogger(backend="csv", csv_path=TEST_CSV_PATH)
        event = events_df.iloc[0].to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        logger.log_steps(lifecycle.run_to_completion())
        assert len(logger.read_all()) > 0

        logger.clear()
        assert len(logger.read_all()) == 0

    def test_audit_row_contains_required_fields(self, events_df, policy_engine, executor):
        event = events_df.iloc[0].to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        history = lifecycle.run_to_completion()

        logger = AuditLogger(backend="csv", csv_path=TEST_CSV_PATH)
        logger.log_steps(history)
        result_df = logger.read_all()

        required = {
            "event_id", "step_number", "simulated_timestamp", "decline_code",
            "cause_category", "diagnosis_rationale", "recovery_probability",
            "policy_action", "policy_rationale", "blocked", "outcome",
        }
        assert required.issubset(set(result_df.columns))

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError):
            AuditLogger(backend="not_a_real_backend")