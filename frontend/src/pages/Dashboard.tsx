import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from "recharts";
import { api, type BatchSummary } from "../api/client";
import RecoveryFunnel from "../components/RecoveryFunnel";

const CAUSE_COLORS: Record<string, string> = {
  insufficient_funds: "#4f8cff",
  expired_card: "#f59e42",
  data_entry_error: "#a78bfa",
  issuer_technical: "#34d399",
  issuer_risk_flag: "#f87171",
};

const STATUS_COLORS: Record<string, string> = {
  recovered: "#34d399",
  escalated: "#f59e42",
  closed_lost: "#f87171",
  open: "#94a3b8",
};

function formatRupees(n: number): string {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export default function Dashboard() {
  const [summary, setSummary] = useState<BatchSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  const load = () => {
    api.getBatchSummary().then(setSummary).catch((e) => setError(e.message));
  };

  useEffect(load, []);

  const handleRunBatch = async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await api.runBatch();
      setSummary(result.metrics);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  };

  if (error) {
    return (
      <div className="empty-state">
        <p>Couldn't load batch summary: {error}</p>
        <p className="hint">Have you run <code>python run_batch.py</code> in the backend yet?</p>
      </div>
    );
  }

  if (!summary) return <div className="empty-state">Loading…</div>;

  const causeChartData = Object.entries(summary.by_cause_category).map(([cause, stats]) => ({
    cause,
    at_risk: stats.amount_at_risk,
    recovered: stats.amount_recovered,
    rate: Math.round(stats.recovery_rate * 100),
  }));

  const statusChartData = Object.entries(summary.status_counts).map(([status, count]) => ({
    name: status,
    value: count,
  }));

  return (
    <div className="page">
      <div className="page-header">
        <h1>Revenue Recovery — Batch Results</h1>
        <button className="btn-primary" onClick={handleRunBatch} disabled={running}>
          {running ? "Running batch…" : "Re-run batch"}
        </button>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Total revenue at risk</div>
          <div className="stat-value">{formatRupees(summary.total_revenue_at_risk)}</div>
          <div className="stat-sub">{summary.n_events} events</div>
        </div>
        <div className="stat-card highlight">
          <div className="stat-label">Revenue recovered</div>
          <div className="stat-value">{formatRupees(summary.total_revenue_recovered)}</div>
          <div className="stat-sub">{(summary.overall_recovery_rate * 100).toFixed(1)}% overall recovery rate</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Capture of recoverable revenue</div>
          <div className="stat-value">{(summary.capture_rate_of_recoverable_revenue * 100).toFixed(1)}%</div>
          <div className="stat-sub">of {formatRupees(summary.baseline_recoverable_revenue_no_intervention)} theoretically recoverable</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Avg attempts per event</div>
          <div className="stat-value">{summary.avg_attempts_per_event}</div>
          <div className="stat-sub">
            {summary.recovered_count} recovered · {summary.escalated_count} escalated · {summary.closed_lost_count} closed lost
          </div>
        </div>
      </div>

      <RecoveryFunnel summary={summary} />

      <div className="chart-grid">
        <div className="chart-card">
          <h3>Revenue at risk vs. recovered, by cause</h3>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={causeChartData} margin={{ left: 10, right: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2a35" />
              <XAxis dataKey="cause" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={70} />
              <YAxis tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(v) => formatRupees(Number(v))} />
              <Legend />
              <Bar dataKey="at_risk" name="At risk" fill="#3b3b48" radius={[4, 4, 0, 0]} />
              <Bar dataKey="recovered" name="Recovered" radius={[4, 4, 0, 0]}>
                {causeChartData.map((entry) => (
                  <Cell key={entry.cause} fill={CAUSE_COLORS[entry.cause] || "#4f8cff"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <h3>Final status breakdown</h3>
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie
                data={statusChartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={100}
                label={(entry) => `${entry.name} (${entry.value})`}
              >
                {statusChartData.map((entry) => (
                  <Cell key={entry.name} fill={STATUS_COLORS[entry.name] || "#94a3b8"} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="chart-card">
        <h3>Recovery rate by cause category</h3>
        <table className="data-table">
          <thead>
            <tr>
              <th>Cause</th>
              <th>Events</th>
              <th>At risk</th>
              <th>Recovered</th>
              <th>Recovery rate</th>
            </tr>
          </thead>
          <tbody>
            {causeChartData
              .sort((a, b) => b.rate - a.rate)
              .map((row) => (
                <tr key={row.cause}>
                  <td>
                    <span className="dot" style={{ background: CAUSE_COLORS[row.cause] }} />
                    {row.cause.replace(/_/g, " ")}
                  </td>
                  <td>{summary.by_cause_category[row.cause].n_events}</td>
                  <td>{formatRupees(row.at_risk)}</td>
                  <td>{formatRupees(row.recovered)}</td>
                  <td>
                    <div className="rate-bar-track">
                      <div className="rate-bar-fill" style={{ width: `${row.rate}%` }} />
                    </div>
                    {row.rate}%
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <p className="footnote">
        {summary.by_cause_category["issuer_risk_flag"] &&
          `Note: issuer_risk_flag (fraud-suspected / do-not-honor) recovers 0% by design — these
          are never auto-contacted, per the compliance policy. This accounts for most of the
          gap between recovered revenue and the theoretical no-intervention baseline.`}
      </p>
    </div>
  );
}
