"""
Tests for the policy engine, executor, and end-to-end single-event pipeline (Day 3).

Run:
    cd backend/tests
    pytest test_policy_and_executor.py -v
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engine"))
from policy import PolicyEngine, AttemptState  # noqa: E402
from executor import RazorpayExecutor, synthetic_indian_mobile  # noqa: E402
from run_single_event import process_one_event, score_event, load_model_bundle  # noqa: E402

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "events.csv")


@pytest.fixture(autouse=True)
def force_mock_razorpay(monkeypatch):
    """Forces mock mode for EVERY test in this file, regardless of what a
    developer's local .env has set for RAZORPAY_MODE. This is essential:
    without it, if a developer sets RAZORPAY_MODE=live to manually test
    the live integration (as intended), the entire test suite silently
    starts making real Razorpay API calls with placeholder test data
    (fake short phone numbers, etc.) and fails or worse, spams the
    account. Tests must be fully isolated from ambient environment state.
    """
    monkeypatch.setenv("RAZORPAY_MODE", "mock")


@pytest.fixture(scope="module")
def policy():
    return PolicyEngine()


@pytest.fixture
def executor():
    # ALWAYS force mock mode in tests, regardless of what a developer's
    # local .env has set (e.g. RAZORPAY_MODE=live for manual live testing).
    # Tests must never depend on ambient environment state or make real
    # API calls with placeholder test data.
    return RazorpayExecutor(mock=True)


# ---------------------------------------------------------------------------
# Policy engine: the compliance-critical behaviors
# ---------------------------------------------------------------------------

class TestPolicyGating:
    def test_issuer_risk_flag_never_auto_acts(self, policy):
        decision = policy.decide("issuer_risk_flag", recovery_probability=0.9,
                                  state=AttemptState(), event_amount=1000)
        assert decision.action == "escalate_human"
        assert decision.blocked is True
        assert decision.block_reason == "compliance_never_auto_action"

    def test_issuer_risk_flag_blocked_even_at_high_score(self, policy):
        # a high model score must NOT override the compliance gate
        decision = policy.decide("issuer_risk_flag", recovery_probability=0.99,
                                  state=AttemptState(), event_amount=1000)
        assert decision.blocked is True

    def test_max_attempts_stops_action(self, policy):
        state = AttemptState(attempt_count=3, last_action_at=datetime.now(timezone.utc) - timedelta(days=1))
        decision = policy.decide("insufficient_funds", recovery_probability=0.9,
                                  state=state, event_amount=1000)
        assert decision.action == "escalate_human"
        assert decision.block_reason == "max_attempts_reached"

    def test_attempts_below_cap_can_still_act(self, policy):
        state = AttemptState(attempt_count=2, last_action_at=datetime.now(timezone.utc) - timedelta(days=1))
        decision = policy.decide("insufficient_funds", recovery_probability=0.9,
                                  state=state, event_amount=1000)
        assert decision.action != "escalate_human" or not decision.blocked

    def test_cooldown_blocks_immediate_repeat_action(self, policy):
        state = AttemptState(attempt_count=1, last_action_at=datetime.now(timezone.utc))
        decision = policy.decide("insufficient_funds", recovery_probability=0.9,
                                  state=state, event_amount=1000)
        assert decision.blocked is True
        assert decision.block_reason in ("cooldown_not_elapsed", "cause_cooldown_not_elapsed")

    def test_recovery_window_exceeded_closes_event(self, policy):
        state = AttemptState(first_detected_at=datetime.now(timezone.utc) - timedelta(days=20))
        decision = policy.decide("insufficient_funds", recovery_probability=0.9,
                                  state=state, event_amount=1000)
        assert decision.action == "hold_closed_lost"
        assert decision.block_reason == "recovery_window_exceeded"

    def test_unknown_cause_escalates_rather_than_guesses(self, policy):
        decision = policy.decide("totally_unknown_cause", recovery_probability=0.9,
                                  state=AttemptState(), event_amount=1000)
        assert decision.action == "escalate_human"
        assert decision.block_reason == "no_policy_rule"


class TestPolicyActionSelection:
    def test_expired_card_always_requests_update_regardless_of_score(self, policy):
        low = policy.decide("expired_card", recovery_probability=0.05,
                             state=AttemptState(), event_amount=1000)
        high = policy.decide("expired_card", recovery_probability=0.95,
                              state=AttemptState(), event_amount=1000)
        assert low.action == "request_card_update"
        assert high.action == "request_card_update"

    def test_high_score_insufficient_funds_retries_immediately(self, policy):
        decision = policy.decide("insufficient_funds", recovery_probability=0.8,
                                  state=AttemptState(), event_amount=1000)
        assert decision.action == "retry_immediate"

    def test_low_score_insufficient_funds_requests_card_update(self, policy):
        decision = policy.decide("insufficient_funds", recovery_probability=0.1,
                                  state=AttemptState(), event_amount=1000)
        assert decision.action == "request_card_update"

    def test_every_decision_has_a_nonempty_rationale(self, policy):
        for cause in ["insufficient_funds", "expired_card", "data_entry_error",
                      "issuer_technical", "issuer_risk_flag"]:
            decision = policy.decide(cause, 0.5, AttemptState(), 1000)
            assert isinstance(decision.rationale, str) and len(decision.rationale) > 15


# ---------------------------------------------------------------------------
# Executor (mock mode)
# ---------------------------------------------------------------------------

class TestExecutorMockMode:
    def test_mock_mode_active_by_default(self):
        executor = RazorpayExecutor(mock=True)
        assert executor.mock is True

    def test_create_payment_link_succeeds(self):
        executor = RazorpayExecutor(mock=True)
        result = executor.create_payment_link(
            event_id="evt_test1", amount_rupees=500.0, customer_name="Test",
            customer_contact=synthetic_indian_mobile("test_customer"), description="test", action_type="retry_immediate",
        )
        assert result.success is True
        assert result.payment_link_id is not None
        assert result.payment_link_url.startswith("https://rzp.io/")
        assert result.mock is True

    def test_same_inputs_give_same_mock_link_id(self):
        executor = RazorpayExecutor(mock=True)
        r1 = executor.create_payment_link("evt_x", 100.0, "A", "+91123", "d", "retry_immediate")
        r2 = executor.create_payment_link("evt_x", 100.0, "A", "+91123", "d", "retry_immediate")
        assert r1.payment_link_id == r2.payment_link_id

    def test_different_action_type_gives_different_link_id(self):
        executor = RazorpayExecutor(mock=True)
        r1 = executor.create_payment_link("evt_x", 100.0, "A", "+91123", "d", "retry_immediate")
        r2 = executor.create_payment_link("evt_x", 100.0, "A", "+91123", "d", "request_card_update")
        assert r1.payment_link_id != r2.payment_link_id

    def test_simulate_outcome_never_succeeds_if_not_recoverable(self):
        for _ in range(20):
            outcome = RazorpayExecutor.simulate_customer_outcome(False, "retry_immediate")
            assert outcome is False


# ---------------------------------------------------------------------------
# End-to-end single event pipeline
# ---------------------------------------------------------------------------

class TestEndToEndSingleEvent:
    @pytest.fixture(scope="class")
    def sample_events(self):
        df = pd.read_csv(DATA_PATH)
        return df

    def test_fraud_event_produces_no_payment_link(self, sample_events):
        fraud_rows = sample_events[sample_events["decline_code"] == "fraud_suspected_by_issuer"]
        if len(fraud_rows) == 0:
            pytest.skip("no fraud_suspected_by_issuer events in this batch")
        event = fraud_rows.iloc[0].to_dict()
        result = process_one_event(event)
        assert result["policy_action"] == "escalate_human"
        assert result["razorpay_payment_link_id"] is None

    def test_insufficient_funds_event_produces_a_link_when_not_blocked(self, sample_events):
        rows = sample_events[sample_events["decline_code"] == "insufficient_funds"]
        event = rows.iloc[0].to_dict()
        result = process_one_event(event)
        if not result["blocked"]:
            assert result["razorpay_payment_link_id"] is not None
            assert result["razorpay_success"] is True

    def test_expired_card_event_forces_card_update_action(self, sample_events):
        rows = sample_events[sample_events["decline_code"] == "card_expired"]
        if len(rows) == 0:
            pytest.skip("no card_expired events in this batch")
        event = rows.iloc[0].to_dict()
        result = process_one_event(event)
        assert result["policy_action"] == "request_card_update"

    def test_result_contains_full_audit_fields(self, sample_events):
        event = sample_events.iloc[0].to_dict()
        result = process_one_event(event)
        required_fields = {
            "event_id", "decline_code", "cause_category", "diagnosis_rationale",
            "recovery_probability", "policy_action", "policy_rationale", "blocked",
        }
        assert required_fields.issubset(result.keys())