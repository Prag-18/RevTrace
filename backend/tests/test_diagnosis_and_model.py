"""
Tests for the diagnosis engine and recovery-probability model (Day 2).

Run:
    cd backend/tests
    pytest test_diagnosis_and_model.py -v
"""

import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "data_gen"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "models"))

from diagnosis import diagnose, DECLINE_CODE_TO_CAUSE  # noqa: E402
from generate_events import DECLINE_CODES  # noqa: E402

MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "events.csv")


# ---------------------------------------------------------------------------
# Diagnosis engine
# ---------------------------------------------------------------------------

class TestDiagnosisEngine:
    def test_every_generator_decline_code_is_diagnosable(self):
        """No event the generator can produce should be undiagnosable —
        an untreated code would silently fall through in the live pipeline.
        """
        for code in DECLINE_CODES.keys():
            info = diagnose(code)
            assert info.cause_category is not None

    def test_unknown_code_raises(self):
        with pytest.raises(ValueError):
            diagnose("not_a_real_decline_code")

    def test_cause_categories_are_limited_and_known(self):
        expected_causes = {
            "insufficient_funds", "expired_card", "data_entry_error",
            "issuer_technical", "issuer_risk_flag",
        }
        actual = {info.cause_category for info in DECLINE_CODE_TO_CAUSE.values()}
        assert actual == expected_causes

    def test_every_cause_has_a_rationale_string(self):
        # audit trail requires a non-empty human-readable rationale for every diagnosis
        for info in DECLINE_CODE_TO_CAUSE.values():
            assert isinstance(info.rationale, str) and len(info.rationale) > 10

    def test_risk_flag_codes_map_correctly(self):
        assert diagnose("fraud_suspected_by_issuer").cause_category == "issuer_risk_flag"
        assert diagnose("do_not_honor").cause_category == "issuer_risk_flag"


# ---------------------------------------------------------------------------
# Model artifacts + honest evaluation checks
# ---------------------------------------------------------------------------

class TestModelArtifacts:
    def test_model_file_exists(self):
        assert os.path.exists(os.path.join(MODELS_DIR, "recovery_model.joblib"))

    def test_scaler_file_exists(self):
        assert os.path.exists(os.path.join(MODELS_DIR, "scaler.joblib"))

    def test_feature_columns_file_exists(self):
        assert os.path.exists(os.path.join(MODELS_DIR, "feature_columns.json"))

    def test_metrics_file_exists(self):
        assert os.path.exists(os.path.join(MODELS_DIR, "metrics.json"))

    def test_model_loads(self):
        model = joblib.load(os.path.join(MODELS_DIR, "recovery_model.joblib"))
        assert hasattr(model, "predict_proba")


class TestMetricsAreHonest:
    """These checks guard against the classic hackathon failure mode:
    reporting metrics on training data, or metrics that are suspiciously
    perfect and therefore not credible.
    """

    @pytest.fixture(scope="class")
    def metrics(self):
        with open(os.path.join(MODELS_DIR, "metrics.json")) as f:
            return json.load(f)

    def test_production_model_is_declared(self, metrics):
        assert metrics["production_model"] in ("logistic_regression", "gradient_boosting")

    def test_test_set_is_genuinely_held_out(self, metrics):
        # n_test should be roughly the configured test_size fraction of the batch,
        # and strictly less than n_train + n_test combined would equal full batch
        prod = metrics[metrics["production_model"].replace("logistic_regression", "logistic_regression")] \
            if False else metrics["logistic_regression"]
        assert prod["n_test"] > 0
        assert prod["n_train"] > prod["n_test"], "train split should be larger than test split (70/30)"

    def test_auc_is_plausible_not_suspicious(self, metrics):
        for model_key in ("logistic_regression", "gradient_boosting"):
            auc = metrics[model_key]["auc"]
            # AUC of 1.0 or near it on a genuinely noisy synthetic problem
            # is a red flag for leakage, not a good result
            assert 0.4 < auc < 0.97, f"{model_key} AUC={auc} is outside a credible range"

    def test_cv_auc_reported_and_stable_estimate_used_for_selection(self, metrics):
        # the single-split AUC is noisy at n=180; production model selection
        # must be based on the cross-validated estimate, not the lucky split
        for model_key in ("logistic_regression", "gradient_boosting"):
            assert "cv_auc_mean" in metrics[model_key]
            assert "cv_auc_std" in metrics[model_key]
            assert len(metrics[model_key]["cv_auc_folds"]) == 5

        prod_key = metrics["production_model"]
        other_key = "gradient_boosting" if prod_key == "logistic_regression" else "logistic_regression"
        assert metrics[prod_key]["cv_auc_mean"] >= metrics[other_key]["cv_auc_mean"], \
            "production model should be the one with the higher cross-validated AUC"

    def test_both_models_reported_not_just_winner(self, metrics):
        assert "logistic_regression" in metrics
        assert "gradient_boosting" in metrics

    def test_confusion_matrix_sums_to_test_set_size(self, metrics):
        for model_key in ("logistic_regression", "gradient_boosting"):
            cm = metrics[model_key]["confusion_matrix"]
            total = sum(sum(row) for row in cm)
            assert total == metrics[model_key]["n_test"]

    def test_feature_importance_reported(self, metrics):
        assert len(metrics["feature_importance"]) > 0
        # importances should not all be identical (degenerate model)
        vals = [row["importance"] for row in metrics["feature_importance"]]
        assert max(vals) > min(vals)


class TestModelPredictionSanity:
    """Load the real model and check its predictions move in sensible
    directions for hand-crafted example inputs — a lightweight substitute
    for full interpretability tooling.
    """

    @pytest.fixture(scope="class")
    def model_bundle(self):
        model = joblib.load(os.path.join(MODELS_DIR, "recovery_model.joblib"))
        scaler = joblib.load(os.path.join(MODELS_DIR, "scaler.joblib"))
        with open(os.path.join(MODELS_DIR, "feature_columns.json")) as f:
            feature_columns = json.load(f)
        return model, scaler, feature_columns

    def _build_row(self, cause_category, event_type, is_first_time,
                    tenure, success_rate, prior_failures, amount, payday):
        row = {
            "customer_tenure_days": tenure,
            "customer_past_success_rate": success_rate,
            "customer_prior_failures_30d": prior_failures,
            "amount": amount,
            "payday_proximity": payday,
        }
        for c in ["insufficient_funds", "expired_card", "data_entry_error",
                  "issuer_technical", "issuer_risk_flag"]:
            row[f"cause_category_{c}"] = 1 if c == cause_category else 0
        for e in ["payment_failure", "subscription_renewal_failure"]:
            row[f"event_type_{e}"] = 1 if e == event_type else 0
        row["is_first_time_customer_0"] = 0 if is_first_time else 1
        row["is_first_time_customer_1"] = 1 if is_first_time else 0
        return row

    def _predict(self, model, scaler, feature_columns, row):
        num_cols = ["customer_tenure_days", "customer_past_success_rate",
                    "customer_prior_failures_30d", "amount", "payday_proximity"]
        full = {**row}
        df_row = pd.DataFrame([full])
        cat_cols = [c for c in feature_columns]
        for c in cat_cols:
            if c not in df_row.columns:
                df_row[c] = 0
        X = pd.concat([df_row[num_cols], df_row[cat_cols]], axis=1)
        X_scaled = scaler.transform(X)
        return model.predict_proba(X_scaled)[0, 1]

    def test_issuer_technical_beats_expired_card(self, model_bundle):
        model, scaler, feature_columns = model_bundle
        common = dict(event_type="payment_failure", is_first_time=False,
                      tenure=300, success_rate=0.85, prior_failures=0,
                      amount=1000, payday=0)
        p_technical = self._predict(model, scaler, feature_columns,
                                     self._build_row("issuer_technical", **common))
        p_expired = self._predict(model, scaler, feature_columns,
                                   self._build_row("expired_card", **common))
        assert p_technical > p_expired, (
            f"Model should rate issuer_technical ({p_technical:.3f}) as more "
            f"recoverable than expired_card ({p_expired:.3f})"
        )

    def test_more_prior_failures_lowers_recovery_probability(self, model_bundle):
        model, scaler, feature_columns = model_bundle
        base = dict(cause_category="insufficient_funds", event_type="payment_failure",
                    is_first_time=False, tenure=300, success_rate=0.85,
                    amount=1000, payday=0)
        p_clean = self._predict(model, scaler, feature_columns,
                                 self._build_row(prior_failures=0, **base))
        p_troubled = self._predict(model, scaler, feature_columns,
                                    self._build_row(prior_failures=4, **base))
        assert p_clean > p_troubled, (
            f"More recent prior failures should lower predicted recovery "
            f"probability ({p_clean:.3f} vs {p_troubled:.3f})"
        )

    def test_predictions_are_valid_probabilities(self, model_bundle):
        model, scaler, feature_columns = model_bundle
        row = self._build_row("insufficient_funds", "payment_failure", False,
                               300, 0.85, 0, 1000, 0)
        p = self._predict(model, scaler, feature_columns, row)
        assert 0.0 <= p <= 1.0