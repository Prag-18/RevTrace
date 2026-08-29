"""
Tests for the synthetic event generator (Day 1).

Run:
    cd backend/tests
    pytest test_data_gen.py -v
"""

import os
import sys

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "data_gen"))
from generate_events import generate_events, DECLINE_CODES, BEST_ACTION_BY_CAUSE  # noqa: E402


@pytest.fixture(scope="module")
def df():
    return generate_events(n=180, seed=42)


class TestSchema:
    def test_row_count(self, df):
        assert len(df) == 180

    def test_expected_columns_present(self, df):
        expected = {
            "event_id", "customer_id", "event_type", "amount", "decline_code",
            "timestamp", "day_of_month", "customer_tenure_days",
            "customer_past_success_rate", "customer_prior_failures_30d",
            "is_first_time_customer", "ground_truth_recovery_prob",
            "ground_truth_recoverable", "ground_truth_best_action",
        }
        assert expected.issubset(set(df.columns))

    def test_no_nulls(self, df):
        assert df.isnull().sum().sum() == 0

    def test_event_ids_unique(self, df):
        assert df["event_id"].is_unique


class TestValueRanges:
    def test_decline_codes_are_known(self, df):
        assert set(df["decline_code"].unique()).issubset(set(DECLINE_CODES.keys()))

    def test_event_types_valid(self, df):
        assert set(df["event_type"].unique()).issubset(
            {"payment_failure", "subscription_renewal_failure"}
        )

    def test_amounts_positive(self, df):
        assert (df["amount"] > 0).all()

    def test_success_rate_in_unit_interval(self, df):
        assert df["customer_past_success_rate"].between(0, 1).all()

    def test_recovery_prob_in_unit_interval(self, df):
        assert df["ground_truth_recovery_prob"].between(0, 1).all()

    def test_day_of_month_valid(self, df):
        assert df["day_of_month"].between(1, 31).all()

    def test_best_action_matches_taxonomy(self, df):
        valid_actions = set(BEST_ACTION_BY_CAUSE.values())
        assert set(df["ground_truth_best_action"].unique()).issubset(valid_actions)


class TestRealism:
    """These are the checks that matter most for hackathon credibility:
    does the synthetic data actually look like a realistic failure batch,
    not a uniform-random toy?
    """

    def test_insufficient_funds_and_expired_card_dominate(self, df):
        # real-world card declines are dominated by these two categories
        top_share = df["decline_code"].isin(
            ["insufficient_funds", "card_expired", "limit_exceeded"]
        ).mean()
        assert top_share > 0.4, "insufficient_funds-family codes should be the plurality"

    def test_fraud_and_do_not_honor_are_rare(self, df):
        rare_share = df["decline_code"].isin(
            ["fraud_suspected_by_issuer", "do_not_honor"]
        ).mean()
        assert rare_share < 0.25, "risk-flag declines should be a minority of events"

    def test_recovery_rate_varies_by_cause(self, df):
        # if every cause recovers at roughly the same rate, the ground truth
        # design has no real signal for a model to learn
        rates = df.groupby("decline_code")["ground_truth_recoverable"].mean()
        assert rates.max() - rates.min() > 0.3, \
            "recovery rate should vary meaningfully across decline codes"

    def test_issuer_technical_recovers_more_than_expired_card(self, df):
        # sanity check on the direction of the effect, not just its existence
        tech_rate = df[df["decline_code"] == "bank_technical_decline"]["ground_truth_recoverable"].mean()
        expired_rate = df[df["decline_code"] == "card_expired"]["ground_truth_recoverable"].mean()
        assert tech_rate > expired_rate, \
            "technical declines should recover more often than expired cards"

    def test_repeat_customers_exist(self, df):
        repeat_share = (df["customer_id"].value_counts() > 1).sum() / df["customer_id"].nunique()
        assert repeat_share > 0.05, "batch should include some repeat-failure customers"

    def test_not_all_events_identical_outcome(self, df):
        # guards against a degenerate generator that always returns the same label
        assert 0.15 < df["ground_truth_recoverable"].mean() < 0.85


class TestReproducibility:
    def test_same_seed_same_output(self):
        df1 = generate_events(n=50, seed=7)
        df2 = generate_events(n=50, seed=7)
        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seed_different_output(self):
        df1 = generate_events(n=50, seed=7)
        df2 = generate_events(n=50, seed=8)
        assert not df1["ground_truth_recoverable"].equals(df2["ground_truth_recoverable"])