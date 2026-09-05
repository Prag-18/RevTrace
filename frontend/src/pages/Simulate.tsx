import { useState } from "react";
import { api, type SimulateRequest, type AuditStep } from "../api/client";
import AuditTimeline from "../components/AuditTimeline";

const DECLINE_CODES: { value: string; label: string; hint: string }[] = [
  { value: "insufficient_funds", label: "Insufficient funds (soft decline)", hint: "Card has insufficient balance — optimal for retry or delayed schedule" },
  { value: "limit_exceeded", label: "Limit exceeded (soft decline)", hint: "Daily/monthly spend limit reached on issuing card" },
  { value: "card_expired", label: "Card expired (hard decline)", hint: "Card validity expired — requires card update or alternate payment link" },
  { value: "invalid_cvv", label: "Invalid CVV (data entry error)", hint: "CVV verification failed — user update requested" },
  { value: "bank_technical_decline", label: "Bank technical decline (network error)", hint: "Generic gateway/bank timeout — immediate retry candidate" },
  { value: "issuer_unavailable", label: "Issuer unavailable (outage)", hint: "Issuing bank system temporarily offline" },
  { value: "do_not_honor", label: "Do not honor (risk flag)", hint: "Issuer generic risk decline — guardrails prevent aggressive retries" },
  { value: "fraud_suspected_by_issuer", label: "Fraud suspected (compliance stop)", hint: "Issuer flagged fraudulent activity — automated contact blocked" },
];

const PRESETS: { name: string; icon: string; req: SimulateRequest }[] = [
  {
    name: "Easy win: Technical glitch",
    icon: "⚡",
    req: {
      decline_code: "bank_technical_decline", amount: 1200, customer_tenure_days: 500,
      customer_past_success_rate: 0.95, customer_prior_failures_30d: 0, day_of_month: 15,
      assume_recoverable: true,
    },
  },
  {
    name: "Compliance Guardrail: Fraud flag",
    icon: "🛡️",
    req: {
      decline_code: "fraud_suspected_by_issuer", amount: 8000, customer_tenure_days: 200,
      customer_past_success_rate: 0.7, customer_prior_failures_30d: 0, day_of_month: 15,
      assume_recoverable: true,
    },
  },
  {
    name: "Multi-attempt: Expired card",
    icon: "🔄",
    req: {
      decline_code: "card_expired", amount: 999, customer_tenure_days: 300,
      customer_past_success_rate: 0.8, customer_prior_failures_30d: 0, day_of_month: 15,
      assume_recoverable: false,
    },
  },
];

export default function Simulate() {
  const [form, setForm] = useState<SimulateRequest>({
    decline_code: "insufficient_funds",
    amount: 1500,
    event_type: "payment_failure",
    customer_tenure_days: 180,
    customer_past_success_rate: 0.85,
    customer_prior_failures_30d: 0,
    is_first_time_customer: false,
    day_of_month: 15,
    assume_recoverable: null,
  });
  const [steps, setSteps] = useState<AuditStep[] | null>(null);
  const [finalStatus, setFinalStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const update = <K extends keyof SimulateRequest>(key: K, value: SimulateRequest[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSteps(null);
    try {
      const result = await api.simulate(form);
      setSteps(result.steps);
      setFinalStatus(result.final_status);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const selectedCode = DECLINE_CODES.find((d) => d.value === form.decline_code);

  return (
    <div className="page">
      <div className="page-header">
        <div className="header-title-group">
          <h1>Hypothetical Scenario Sandbox</h1>
          <p className="header-subtitle">
            Test custom payment failure events against the live autonomous policy engine in isolation
          </p>
        </div>
      </div>

      <div style={{ marginBottom: 20 }}>
        <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text-secondary)", display: "block", marginBottom: 10 }}>
          Load Scenario Preset:
        </span>
        <div className="sim-presets">
          {PRESETS.map((p) => (
            <button key={p.name} type="button" className="pill" onClick={() => setForm(p.req)}>
              <span style={{ marginRight: 6 }}>{p.icon}</span>
              <span>{p.name}</span>
            </button>
          ))}
        </div>
      </div>

      <form className="sim-form" onSubmit={handleSubmit}>
        <div className="sim-form-grid">
          <label>
            <span>Decline Reason Code</span>
            <select value={form.decline_code} onChange={(e) => update("decline_code", e.target.value)}>
              {DECLINE_CODES.map((d) => (
                <option key={d.value} value={d.value}>{d.label}</option>
              ))}
            </select>
            {selectedCode && <span className="field-hint">{selectedCode.hint}</span>}
          </label>

          <label>
            <span>Transaction Amount (₹)</span>
            <input
              type="number" min={1} step="1"
              value={form.amount}
              onChange={(e) => update("amount", Number(e.target.value))}
            />
          </label>

          <label>
            <span>Event Category</span>
            <select value={form.event_type} onChange={(e) => update("event_type", e.target.value)}>
              <option value="payment_failure">Standard One-Off Payment Failure</option>
              <option value="subscription_renewal_failure">Recurring Subscription Renewal Failure</option>
            </select>
          </label>

          <label>
            <span>Customer Account Tenure (Days)</span>
            <input
              type="number" min={0}
              value={form.customer_tenure_days}
              onChange={(e) => update("customer_tenure_days", Number(e.target.value))}
            />
          </label>

          <label>
            <div style={{ display: "flex", justifyContent: "space-between" }}>
              <span>Historical Success Rate</span>
              <strong style={{ color: "#818cf8", fontFamily: "var(--font-mono)" }}>
                {((form.customer_past_success_rate ?? 0) * 100).toFixed(0)}%
              </strong>
            </div>
            <input
              type="range" min={0} max={1} step={0.01}
              value={form.customer_past_success_rate}
              onChange={(e) => update("customer_past_success_rate", Number(e.target.value))}
            />
          </label>

          <label>
            <span>Prior Failures (Last 30 Days)</span>
            <input
              type="number" min={0}
              value={form.customer_prior_failures_30d}
              onChange={(e) => update("customer_prior_failures_30d", Number(e.target.value))}
            />
          </label>

          <label>
            <span>Billing Day of Month (1 - 31)</span>
            <input
              type="number" min={1} max={31}
              value={form.day_of_month}
              onChange={(e) => update("day_of_month", Number(e.target.value))}
            />
          </label>

          <label className="checkbox-label" style={{ alignSelf: "center", marginTop: 12 }}>
            <input
              type="checkbox"
              checked={form.is_first_time_customer}
              onChange={(e) => update("is_first_time_customer", e.target.checked)}
            />
            <span>First-time Customer</span>
          </label>
        </div>

        <div className="sim-outcome-select">
          <span>Simulated Customer Environment:</span>
          <div className="filter-pills">
            <button
              type="button"
              className={`pill ${form.assume_recoverable === true ? "pill-active" : ""}`}
              onClick={() => update("assume_recoverable", true)}
            >
              ✓ Assume Customer Will Pay (Recoverable)
            </button>
            <button
              type="button"
              className={`pill ${form.assume_recoverable === false ? "pill-active" : ""}`}
              onClick={() => update("assume_recoverable", false)}
            >
              ✕ Assume Customer Never Pays (Unrecoverable)
            </button>
            <button
              type="button"
              className={`pill ${form.assume_recoverable === null ? "pill-active" : ""}`}
              onClick={() => update("assume_recoverable", null)}
            >
              ⚙ Decision Steps Only (No Customer Reaction)
            </button>
          </div>
        </div>

        <button className="btn-primary" type="submit" disabled={loading} style={{ width: "100%", justifyContent: "center" }}>
          {loading ? (
            <>
              <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
              <span>Simulating Pipeline Execution…</span>
            </>
          ) : (
            <>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              <span>Run Scenario Simulation</span>
            </>
          )}
        </button>
      </form>

      {error && (
        <div className="empty-state">
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
          </svg>
          <p style={{ fontWeight: 700, color: "#fff" }}>Simulation Error: {error}</p>
        </div>
      )}

      {steps && (
        <div className="chart-card" style={{ marginTop: 28 }}>
          <div className="page-header" style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 18, color: "#fff", display: "flex", alignItems: "center", gap: 8 }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2.5">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              Simulation Audit Results
            </h3>
            {finalStatus && (
              <span className={`badge badge-lg ${
                finalStatus === "recovered" ? "badge-success" :
                finalStatus === "escalated" ? "badge-warning" :
                finalStatus === "closed_lost" ? "badge-danger" : "badge-neutral"
              }`}>
                Final Status: {finalStatus.replace(/_/g, " ")}
              </span>
            )}
          </div>
          <AuditTimeline steps={steps} />
        </div>
      )}
    </div>
  );
}
