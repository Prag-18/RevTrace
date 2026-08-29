"""
Train + evaluate the recovery-probability model.

    P(recovery | cause_category, customer history, timing, event_type)

Trained on 70% of the synthetic batch, evaluated HONESTLY on the
remaining held-out 30% — the metrics printed/saved here are what should
be reported in the pitch, not cherry-picked numbers from the training set.

Run:
    python train_recovery_model.py --events ../data/events.csv --out_dir ../models
"""

import argparse
import json
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    roc_auc_score, precision_recall_curve, average_precision_score,
    precision_score, recall_score, f1_score, brier_score_loss, confusion_matrix
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "engine"))
from diagnosis import diagnose  # noqa: E402


FEATURE_COLUMNS_NUMERIC = [
    "customer_tenure_days",
    "customer_past_success_rate",
    "customer_prior_failures_30d",
    "amount",
    "payday_proximity",  # engineered below
]
FEATURE_COLUMNS_CATEGORICAL = [
    "cause_category",
    "event_type",
    "is_first_time_customer",
]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build the model-ready feature frame from raw events.

    IMPORTANT: this function only uses fields the live pipeline would
    actually have at diagnosis time (decline_code + customer history).
    It never touches ground_truth_* columns except to keep the label
    alongside for training/eval convenience — those are dropped before
    fitting.
    """
    df = df.copy()

    # cause_category comes from the deterministic rules engine, not a guess
    df["cause_category"] = df["decline_code"].apply(lambda c: diagnose(c).cause_category)

    # payday proximity: within 5 days of month start/end
    df["payday_proximity"] = df["day_of_month"].apply(
        lambda d: 1 if (d <= 5 or d >= 26) else 0
    )

    df["is_first_time_customer"] = df["is_first_time_customer"].astype(int)

    return df


def build_design_matrix(df: pd.DataFrame, encoder_categories=None):
    """One-hot encode categoricals, standardize numerics.
    Returns X, feature_names, and the fitted categories (for reuse at inference time).
    """
    cat_df = pd.get_dummies(df[FEATURE_COLUMNS_CATEGORICAL].astype(str), prefix=FEATURE_COLUMNS_CATEGORICAL)

    if encoder_categories is not None:
        # align columns to training-time schema (fill missing with 0, drop unseen)
        cat_df = cat_df.reindex(columns=encoder_categories, fill_value=0)

    num_df = df[FEATURE_COLUMNS_NUMERIC].reset_index(drop=True)
    cat_df = cat_df.reset_index(drop=True)

    X = pd.concat([num_df, cat_df], axis=1)
    return X, list(cat_df.columns)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=str, default="../data/events.csv")
    parser.add_argument("--out_dir", type=str, default="../models")
    parser.add_argument("--test_size", type=float, default=0.3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    df = pd.read_csv(args.events)
    df = engineer_features(df)

    y = df["ground_truth_recoverable"].astype(int)

    # --- train/test split, stratified so both splits have a realistic
    # mix of recoverable/non-recoverable events ---
    train_df, test_df, y_train, y_test = train_test_split(
        df, y, test_size=args.test_size, random_state=args.seed, stratify=y
    )

    X_train, feature_columns = build_design_matrix(train_df)
    X_test, _ = build_design_matrix(test_df, encoder_categories=feature_columns)

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # --- model: Gradient Boosting (robust default, no extra native-lib
    # dependency risk vs LightGBM in a hackathon environment) ---
    model = GradientBoostingClassifier(
        n_estimators=150, max_depth=3, learning_rate=0.08, random_state=args.seed
    )
    model.fit(X_train_scaled, y_train)

    # a simple logistic regression baseline, reported alongside for honesty
    # (shows the GBM is actually adding value, not just complexity)
    baseline = LogisticRegression(max_iter=1000)
    baseline.fit(X_train_scaled, y_train)

    # --- evaluate on the HELD-OUT test set only ---
    def evaluate(m, name):
        proba = m.predict_proba(X_test_scaled)[:, 1]
        preds_at_50 = (proba >= 0.5).astype(int)

        auc = roc_auc_score(y_test, proba)
        ap = average_precision_score(y_test, proba)
        brier = brier_score_loss(y_test, proba)
        precision = precision_score(y_test, preds_at_50, zero_division=0)
        recall = recall_score(y_test, preds_at_50, zero_division=0)
        f1 = f1_score(y_test, preds_at_50, zero_division=0)
        cm = confusion_matrix(y_test, preds_at_50).tolist()

        print(f"\n=== {name} (held-out test set, n={len(y_test)}) ===")
        print(f"  ROC AUC:          {auc:.3f}")
        print(f"  Avg Precision:    {ap:.3f}")
        print(f"  Brier score:      {brier:.3f}  (lower is better; measures calibration)")
        print(f"  Precision @0.5:   {precision:.3f}")
        print(f"  Recall @0.5:      {recall:.3f}")
        print(f"  F1 @0.5:          {f1:.3f}")
        print(f"  Confusion matrix: {cm}  [[TN, FP], [FN, TP]]")

        return {
            "auc": round(auc, 4),
            "average_precision": round(ap, 4),
            "brier_score": round(brier, 4),
            "precision_at_0.5": round(precision, 4),
            "recall_at_0.5": round(recall, 4),
            "f1_at_0.5": round(f1, 4),
            "confusion_matrix": cm,
            "n_test": int(len(y_test)),
            "n_train": int(len(y_train)),
            "positive_rate_test": round(float(y_test.mean()), 4),
        }

    gbm_metrics = evaluate(model, "GradientBoostingClassifier")
    baseline_metrics = evaluate(baseline, "LogisticRegression (baseline)")

    # --- select the PRODUCTION model based on held-out AUC, not vanity ---
    # With a small batch (n=180) a simpler model can genuinely generalize
    # better than a more flexible one. We pick whichever wins on the
    # held-out set and say so explicitly, rather than always shipping the
    # more sophisticated-looking model.
    if gbm_metrics["auc"] >= baseline_metrics["auc"]:
        production_model, production_name, production_metrics = model, "gradient_boosting", gbm_metrics
    else:
        production_model, production_name, production_metrics = baseline, "logistic_regression", baseline_metrics

    print(f"\n>>> Selected PRODUCTION model: {production_name} "
          f"(held-out AUC {production_metrics['auc']:.3f} vs. "
          f"{'baseline' if production_name=='gradient_boosting' else 'gbm'} "
          f"{(baseline_metrics if production_name=='gradient_boosting' else gbm_metrics)['auc']:.3f})")

    # precision-recall curve points, computed for the PRODUCTION model
    proba_test = production_model.predict_proba(X_test_scaled)[:, 1]
    prec_curve, rec_curve, thresh_curve = precision_recall_curve(y_test, proba_test)
    pr_curve_data = [
        {"threshold": float(t), "precision": float(p), "recall": float(r)}
        for p, r, t in zip(prec_curve[:-1], rec_curve[:-1], thresh_curve)
    ]

    # feature importances / coefficients, whichever the production model supports
    if hasattr(production_model, "feature_importances_"):
        importances = sorted(
            zip(X_train.columns, production_model.feature_importances_),
            key=lambda x: -x[1]
        )
    else:
        # logistic regression: use absolute standardized coefficient magnitude
        importances = sorted(
            zip(X_train.columns, np.abs(production_model.coef_[0])),
            key=lambda x: -x[1]
        )
    feature_importance_data = [{"feature": f, "importance": round(float(i), 4)} for f, i in importances]

    # --- persist artifacts (always named recovery_model.* regardless of
    # which algorithm won, so downstream code doesn't care) ---
    joblib.dump(production_model, os.path.join(args.out_dir, "recovery_model.joblib"))
    joblib.dump(scaler, os.path.join(args.out_dir, "scaler.joblib"))
    with open(os.path.join(args.out_dir, "feature_columns.json"), "w") as f:
        json.dump(feature_columns, f, indent=2)

    metrics_report = {
        "production_model": production_name,
        "gradient_boosting": gbm_metrics,
        "logistic_regression": baseline_metrics,
        "precision_recall_curve": pr_curve_data,
        "feature_importance": feature_importance_data,
    }
    with open(os.path.join(args.out_dir, "metrics.json"), "w") as f:
        json.dump(metrics_report, f, indent=2)

    print(f"\nSaved model ({production_name}), scaler, feature schema, and metrics.json -> {args.out_dir}")
    print("\nTop features driving the production model:")
    for row in feature_importance_data[:8]:
        print(f"  {row['feature']:35s} {row['importance']:.4f}")


if __name__ == "__main__":
    main()