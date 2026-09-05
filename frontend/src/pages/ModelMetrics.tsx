import { useEffect, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell, ErrorBar,
} from "recharts";
import { api, type ModelMetrics as ModelMetricsType } from "../api/client";

export default function ModelMetrics() {
  const [metrics, setMetrics] = useState<ModelMetricsType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getModelMetrics().then(setMetrics).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="empty-state">
        <p>Couldn't load model metrics: {error}</p>
        <p className="hint">Have you run <code>python train_recovery_model.py</code> yet?</p>
      </div>
    );
  }
  if (!metrics) return <div className="empty-state">Loading…</div>;

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

  const prCurveData = metrics.precision_recall_curve.filter((_, i) => i % 3 === 0);

  const productionMetrics =
    metrics.production_model === "logistic_regression"
      ? metrics.logistic_regression
      : metrics.gradient_boosting;

  const cm = productionMetrics.confusion_matrix;

  return (
    <div className="page">
      <div className="page-header">
        <h1>Recovery Model — Evaluation</h1>
      </div>

      <div className="callout">
        Production model selected: <strong>{metrics.production_model.replace(/_/g, " ")}</strong>{" "}
        — chosen by 5-fold cross-validated AUC, not a single train/test split, since a lucky or
        unlucky split can swing AUC by ±0.1 or more on a batch this size.
      </div>

      <div className="chart-grid">
        <div className="chart-card">
          <h3>5-fold cross-validated AUC (with std. dev.)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={cvChartData} margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a35" />
              <XAxis dataKey="model" />
              <YAxis domain={[0, 1]} />
              <Tooltip formatter={(v) => Number(v).toFixed(3)} />
              <Bar dataKey="cv_auc" radius={[4, 4, 0, 0]}>
                {cvChartData.map((entry) => (
                  <Cell key={entry.model} fill={entry.isProduction ? "#34d399" : "#3b3b48"} />
                ))}
                <ErrorBar dataKey="error" width={6} stroke="#94a3b8" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="hint">Green = selected as production model.</p>
        </div>

        <div className="chart-card">
          <h3>Precision-recall curve (production model)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={prCurveData} margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a35" />
              <XAxis dataKey="recall" domain={[0, 1]} tickFormatter={(v) => v.toFixed(1)} />
              <YAxis domain={[0, 1]} tickFormatter={(v) => v.toFixed(1)} />
              <Tooltip formatter={(v) => Number(v).toFixed(3)} />
              <Line type="monotone" dataKey="precision" stroke="#4f8cff" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="chart-grid">
        <div className="chart-card">
          <h3>Feature importance</h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart
              data={metrics.feature_importance.slice(0, 10)}
              layout="vertical"
              margin={{ left: 40, right: 20 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a35" />
              <XAxis type="number" />
              <YAxis type="category" dataKey="feature" width={180} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => Number(v).toFixed(3)} />
              <Bar dataKey="importance" fill="#4f8cff" radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <h3>Confusion matrix (held-out test set, n={productionMetrics.n_test})</h3>
          <table className="confusion-matrix">
            <tbody>
              <tr>
                <td className="cm-label"></td>
                <td className="cm-header">Predicted: No</td>
                <td className="cm-header">Predicted: Yes</td>
              </tr>
              <tr>
                <td className="cm-header">Actual: No</td>
                <td className="cm-cell cm-correct">{cm[0][0]}</td>
                <td className="cm-cell cm-wrong">{cm[0][1]}</td>
              </tr>
              <tr>
                <td className="cm-header">Actual: Yes</td>
                <td className="cm-cell cm-wrong">{cm[1][0]}</td>
                <td className="cm-cell cm-correct">{cm[1][1]}</td>
              </tr>
            </tbody>
          </table>
          <div className="metric-list">
            <div><span>Precision</span><strong>{(productionMetrics.precision_at_0_5 ?? 0).toFixed(3)}</strong></div>
            <div><span>Recall</span><strong>{(productionMetrics.recall_at_0_5 ?? 0).toFixed(3)}</strong></div>
            <div><span>Brier score (lower is better)</span><strong>{productionMetrics.brier_score.toFixed(3)}</strong></div>
          </div>
        </div>
      </div>
    </div>
  );
}

