import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, ErrorBar,
} from "recharts";
import { api, type ModelMetrics as ModelMetricsType } from "../api/client";

// Custom Tooltip Component for Model Metrics
const CustomMetricTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <div className="custom-tooltip-title">{String(label)}</div>
        {payload.map((entry: any, index: number) => (
          <div key={`item-${index}`} className="custom-tooltip-item">
            <span style={{ color: entry.color || entry.fill }}>{entry.name}:</span>
            <span className="custom-tooltip-value">
              {typeof entry.value === "number" ? entry.value.toFixed(3) : entry.value}
            </span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

export default function ModelMetrics() {
  const [metrics, setMetrics] = useState<ModelMetricsType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.getModelMetrics()
      .then(setMetrics)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (error) {
    return (
      <div className="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <p style={{ fontWeight: 700, color: "#fff" }}>Unable to load model metrics</p>
        <p className="hint">{error}</p>
        <button className="btn-secondary" onClick={load}>Retry</button>
      </div>
    );
  }

  if (loading || !metrics) {
    return (
      <div className="empty-state">
        <div className="spinner"></div>
        <p>Loading machine learning diagnostics...</p>
      </div>
    );
  }

  const cvChartData = [
    {
      model: "Logistic Regression",
      cv_auc: metrics.logistic_regression.cv_auc_mean,
      error: metrics.logistic_regression.cv_auc_std,
      isProduction: metrics.production_model === "logistic_regression",
    },
    {
      model: "Gradient Boosting",
      cv_auc: metrics.gradient_boosting.cv_auc_mean,
      error: metrics.gradient_boosting.cv_auc_std,
      isProduction: metrics.production_model === "gradient_boosting",
    },
  ];

  const prCurveData = metrics.precision_recall_curve.filter((_, i) => i % 2 === 0);

  const productionMetrics =
    metrics.production_model === "logistic_regression"
      ? metrics.logistic_regression
      : metrics.gradient_boosting;

  const cm = productionMetrics.confusion_matrix;

  return (
    <div className="page">
      <div className="page-header">
        <div className="header-title-group">
          <h1>Recovery Model Performance & ML Diagnostics</h1>
          <p className="header-subtitle">
            Cross-validation comparisons, precision-recall thresholds, and feature importances
          </p>
        </div>
      </div>

      <div className="callout">
        <div className="callout-icon-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#a5b4fc" strokeWidth="2.5">
            <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
          </svg>
          <span>Production Model: {metrics.production_model.replace(/_/g, " ").toUpperCase()}</span>
        </div>
        <p>
          Selected via rigorous 5-fold stratified cross-validation AUC ({productionMetrics.cv_auc_mean.toFixed(3)} ± {productionMetrics.cv_auc_std.toFixed(3)}) rather than a single random train/test split, ensuring stability against sample variance on edge decline codes.
        </p>
      </div>

      <div className="chart-grid">
        <div className="chart-card">
          <div className="chart-header">
            <h3>5-Fold Cross-Validated AUC Comparison</h3>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={cvChartData} margin={{ left: 10, right: 20, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="model" tick={{ fontSize: 12, fill: "#94a3b8" }} />
              <YAxis domain={[0, 1]} tick={{ fontSize: 12, fill: "#94a3b8" }} />
              <Tooltip content={<CustomMetricTooltip />} />
              <Bar dataKey="cv_auc" name="Mean CV AUC" radius={[6, 6, 0, 0]}>
                {cvChartData.map((entry) => (
                  <Cell key={entry.model} fill={entry.isProduction ? "#10b981" : "#2a2e3f"} />
                ))}
                <ErrorBar dataKey="error" width={8} stroke="#818cf8" strokeWidth={2} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", gap: 16, marginTop: 12, fontSize: 12, color: "var(--text-muted)" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="dot" style={{ background: "#10b981" }} /> Selected Production Model
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="dot" style={{ background: "#2a2e3f" }} /> Alternative Architecture
            </span>
          </div>
        </div>

        <div className="chart-card">
          <div className="chart-header">
            <h3>Precision-Recall Tradeoff Curve</h3>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={prCurveData} margin={{ left: 10, right: 20, bottom: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="recall" domain={[0, 1]} tickFormatter={(v) => v.toFixed(1)} tick={{ fontSize: 12, fill: "#94a3b8" }} />
              <YAxis domain={[0, 1]} tickFormatter={(v) => v.toFixed(1)} tick={{ fontSize: 12, fill: "#94a3b8" }} />
              <Tooltip content={<CustomMetricTooltip />} />
              <Line type="monotone" dataKey="precision" name="Precision" stroke="#6366f1" strokeWidth={3} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="chart-grid">
        <div className="chart-card">
          <div className="chart-header">
            <h3>Top Feature Importances (Model Drivers)</h3>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={metrics.feature_importance.slice(0, 8)}
              layout="vertical"
              margin={{ left: 40, right: 20, bottom: 10 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis type="number" tick={{ fontSize: 11, fill: "#94a3b8" }} />
              <YAxis type="category" dataKey="feature" width={170} tick={{ fontSize: 11, fill: "#cbd5e1" }} />
              <Tooltip content={<CustomMetricTooltip />} />
              <Bar dataKey="importance" name="Relative Weight" fill="#6366f1" radius={[0, 4, 4, 0]}>
                {metrics.feature_importance.slice(0, 8).map((_, index) => (
                  <Cell key={`cell-${index}`} fill={index === 0 ? "#818cf8" : "#6366f1"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <div className="chart-header">
            <h3>Held-Out Test Confusion Matrix (n={productionMetrics.n_test})</h3>
          </div>
          <table className="confusion-matrix">
            <tbody>
              <tr>
                <td className="cm-header"></td>
                <td className="cm-header">Predicted Unrecoverable</td>
                <td className="cm-header">Predicted Recoverable</td>
              </tr>
              <tr>
                <td className="cm-header">Actual Unrecoverable</td>
                <td className="cm-cell cm-correct">
                  <div>{cm[0][0]}</div>
                  <span style={{ fontSize: 11, fontWeight: 500, opacity: 0.8 }}>True Negative</span>
                </td>
                <td className="cm-cell cm-wrong">
                  <div>{cm[0][1]}</div>
                  <span style={{ fontSize: 11, fontWeight: 500, opacity: 0.8 }}>False Positive</span>
                </td>
              </tr>
              <tr>
                <td className="cm-header">Actual Recoverable</td>
                <td className="cm-cell cm-wrong">
                  <div>{cm[1][0]}</div>
                  <span style={{ fontSize: 11, fontWeight: 500, opacity: 0.8 }}>False Negative</span>
                </td>
                <td className="cm-cell cm-correct">
                  <div>{cm[1][1]}</div>
                  <span style={{ fontSize: 11, fontWeight: 500, opacity: 0.8 }}>True Positive</span>
                </td>
              </tr>
            </tbody>
          </table>

          <div className="metric-list">
            <div className="metric-list-item">
              <span>Decision Threshold Precision (at 0.5)</span>
              <strong>{((productionMetrics.precision_at_0_5 ?? 0) * 100).toFixed(1)}%</strong>
            </div>
            <div className="metric-list-item">
              <span>Decision Threshold Recall (at 0.5)</span>
              <strong>{((productionMetrics.recall_at_0_5 ?? 0) * 100).toFixed(1)}%</strong>
            </div>
            <div className="metric-list-item">
              <span>Brier Calibration Score (Lower is better)</span>
              <strong>{productionMetrics.brier_score.toFixed(3)}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
