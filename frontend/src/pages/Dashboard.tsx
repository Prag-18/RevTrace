import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
} from "recharts";
import { api, type BatchSummary } from "../api/client";

const CAUSE_COLORS: Record<string, string> = {
  insufficient_funds: "#6366f1",
  expired_card: "#f59e0b",
  data_entry_error: "#a855f7",
  issuer_technical: "#06b6d4",
  issuer_risk_flag: "#f43f5e",
};

const STATUS_COLORS: Record<string, string> = {
  recovered: "#10b981",
  escalated: "#f59e0b",
  closed_lost: "#f43f5e",
  open: "#94a3b8",
};

function formatRupees(n: number): string {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

// Custom Tooltip Component for Recharts
const CustomBarTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    return (
      <div className="custom-tooltip">
        <div className="custom-tooltip-title">{String(label).replace(/_/g, " ")}</div>
        {payload.map((entry: any, index: number) => (
          <div key={`item-${index}`} className="custom-tooltip-item">
            <span style={{ color: entry.color || entry.fill }}>{entry.name}:</span>
            <span className="custom-tooltip-value">{formatRupees(Number(entry.value))}</span>
          </div>
        ))}
      </div>
    );
  }
  return null;
};

const CustomPieTooltip = ({ active, payload }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0];
    return (
      <div className="custom-tooltip">
        <div className="custom-tooltip-title">{String(data.name).replace(/_/g, " ")}</div>
        <div className="custom-tooltip-item">
          <span style={{ color: data.payload.fill }}>Count:</span>
          <span className="custom-tooltip-value">{data.value} events</span>
        </div>
      </div>
    );
  }
  return null;
};

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
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <p style={{ fontWeight: 700, color: "#fff" }}>Unable to load batch summary</p>
        <p className="hint">{error}</p>
        <button className="btn-secondary" onClick={load}>Retry</button>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="empty-state">
        <div className="spinner"></div>
        <p>Loading recovery intelligence...</p>
      </div>
    );
  }

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

  const stages = [
    { key: "recovered", label: "Recovered", color: "#10b981" },
    { key: "escalated", label: "Escalated", color: "#f59e0b" },
    { key: "closed_lost", label: "Closed Lost", color: "#f43f5e" },
  ] as const;
  const totalEvents = summary.n_events || 1;

  return (
    <div className="page">
      <div className="page-header">
        <div className="header-title-group">
          <h1>Revenue Recovery Pipeline</h1>
          <p className="header-subtitle">
            Autonomous diagnosis, ML scoring, and policy execution for failed payments
          </p>
        </div>
        <button className="btn-primary" onClick={handleRunBatch} disabled={running}>
          {running ? (
            <>
              <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              <span>Running Simulation…</span>
            </>
          ) : (
            <>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 4 23 10 17 10" />
                <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
              </svg>
              <span>Re-run Batch</span>
            </>
          )}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
            </svg>
          </div>
          <div className="stat-label">Total Revenue at Risk</div>
          <div className="stat-value">{formatRupees(summary.total_revenue_at_risk)}</div>
          <div className="stat-sub">
            <span>{summary.n_events} failed events tracked</span>
          </div>
        </div>

        <div className="stat-card highlight">
          <div className="stat-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
          <div className="stat-label">Revenue Recovered</div>
          <div className="stat-value">{formatRupees(summary.total_revenue_recovered)}</div>
          <div className="stat-sub">
            <strong style={{ color: "#34d399" }}>{(summary.overall_recovery_rate * 100).toFixed(1)}%</strong>
            <span>overall recovery rate</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div className="stat-label">Capture of Recoverable</div>
          <div className="stat-value">{(summary.capture_rate_of_recoverable_revenue * 100).toFixed(1)}%</div>
          <div className="stat-sub">
            <span>of {formatRupees(summary.baseline_recoverable_revenue_no_intervention)} recoverable pool</span>
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-icon-wrapper">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
          </div>
          <div className="stat-label">Avg Attempts Per Event</div>
          <div className="stat-value">{summary.avg_attempts_per_event}</div>
          <div className="stat-sub">
            <span>{summary.recovered_count} rec · {summary.escalated_count} esc · {summary.closed_lost_count} lost</span>
          </div>
        </div>
      </div>

      {/* Recovery Funnel */}
      <div className="chart-card" style={{ marginBottom: 24 }}>
        <div className="chart-header">
          <h3>Lifecycle Status Funnel</h3>
          <span className="hint">{summary.n_events} total events</span>
        </div>
        <div className="funnel-container">
          {stages.map((st) => {
            const count = summary.status_counts[st.key] ?? 0;
            const pct = ((count / totalEvents) * 100).toFixed(1);
            return (
              <div className="funnel-step" key={st.key}>
                <div className="funnel-step-header">
                  <span className="funnel-title" style={{ color: st.color }}>{st.label}</span>
                  <span className="badge badge-neutral">{pct}%</span>
                </div>
                <div className="funnel-value">{count} <span style={{ fontSize: 13, color: "var(--text-muted)", fontWeight: 500 }}>events</span></div>
                <div className="funnel-bar-track">
                  <div className="funnel-bar-fill" style={{ width: `${pct}%`, background: st.color }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Charts Grid */}
      <div className="chart-grid">
        <div className="chart-card">
          <div className="chart-header">
            <h3>Revenue at Risk vs. Recovered by Cause</h3>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <BarChart data={causeChartData} margin={{ left: 10, right: 20, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="cause" tick={{ fontSize: 11, fill: "#94a3b8" }} interval={0} angle={-20} textAnchor="end" height={60} />
              <YAxis tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11, fill: "#94a3b8" }} />
              <Tooltip content={<CustomBarTooltip />} />
              <Legend wrapperStyle={{ paddingTop: 10 }} />
              <Bar dataKey="at_risk" name="At Risk" fill="#2a2e3f" radius={[4, 4, 0, 0]} />
              <Bar dataKey="recovered" name="Recovered" radius={[4, 4, 0, 0]}>
                {causeChartData.map((entry) => (
                  <Cell key={entry.cause} fill={CAUSE_COLORS[entry.cause] || "#6366f1"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-card">
          <div className="chart-header">
            <h3>Outcome Distribution</h3>
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie
                data={statusChartData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={105}
                paddingAngle={4}
                label={({ name, percent }: any) => `${name} (${((percent || 0) * 100).toFixed(0)}%)`}
              >
                {statusChartData.map((entry) => (
                  <Cell key={entry.name} fill={STATUS_COLORS[entry.name] || "#94a3b8"} stroke="rgba(0,0,0,0.4)" />
                ))}
              </Pie>
              <Tooltip content={<CustomPieTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Recovery Rate Table */}
      <div className="chart-card">
        <div className="chart-header">
          <h3>Cause-Level Recovery Efficiency</h3>
        </div>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Cause Category</th>
                <th>Events</th>
                <th>Revenue at Risk</th>
                <th>Recovered</th>
                <th>Recovery Rate</th>
              </tr>
            </thead>
            <tbody>
              {causeChartData
                .sort((a, b) => b.rate - a.rate)
                .map((row) => (
                  <tr key={row.cause}>
                    <td>
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <span className="dot" style={{ background: CAUSE_COLORS[row.cause] || "#6366f1" }} />
                        <strong style={{ textTransform: "capitalize" }}>{row.cause.replace(/_/g, " ")}</strong>
                      </div>
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)" }}>{summary.by_cause_category[row.cause].n_events}</td>
                    <td style={{ fontFamily: "var(--font-mono)" }}>{formatRupees(row.at_risk)}</td>
                    <td style={{ fontFamily: "var(--font-mono)", color: "#34d399", fontWeight: 700 }}>
                      {formatRupees(row.recovered)}
                    </td>
                    <td>
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <div className="rate-bar-track">
                          <div className="rate-bar-fill" style={{ width: `${row.rate}%`, background: CAUSE_COLORS[row.cause] || "#6366f1" }} />
                        </div>
                        <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>{row.rate}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      <p className="footnote">
        {summary.by_cause_category["issuer_risk_flag"] &&
          `Note: Issuer Risk Flag events (fraud suspected / do not honor) intentionally recover 0% per compliance guardrails. 
          The agent blocks automatic customer contact for flagged cards to prevent merchant chargebacks.`}
      </p>
    </div>
  );
}
