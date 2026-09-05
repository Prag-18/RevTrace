import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, type AuditStep } from "../api/client";
import AuditTimeline from "../components/AuditTimeline";

function formatRupees(n: number): string {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export default function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  const [steps, setSteps] = useState<AuditStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!eventId) return;
    setLoading(true);
    api.getEventAudit(eventId)
      .then((d) => setSteps(d.steps))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [eventId]);

  if (error) {
    return (
      <div className="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <p style={{ fontWeight: 700, color: "#fff" }}>Couldn't load audit trail for {eventId}</p>
        <p className="hint">{error}</p>
        <Link to="/events" className="btn-secondary" style={{ textDecoration: "none" }}>← Back to Events</Link>
      </div>
    );
  }

  if (loading || steps.length === 0) {
    return (
      <div className="empty-state">
        <div className="spinner"></div>
        <p>Loading decision trail for {eventId}...</p>
      </div>
    );
  }

  const first = steps[0];
  const last = steps[steps.length - 1];

  const statusClass =
    last.event_status_after === "recovered"
      ? "badge-success"
      : last.event_status_after === "escalated"
      ? "badge-warning"
      : last.event_status_after === "closed_lost"
      ? "badge-danger"
      : "badge-neutral";

  return (
    <div className="page">
      <Link to="/events" className="back-link">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="19" y1="12" x2="5" y2="12" />
          <polyline points="12 19 5 12 12 5" />
        </svg>
        <span>Back to Events List</span>
      </Link>

      <div className="page-header" style={{ marginTop: 8 }}>
        <div className="header-title-group">
          <h1 style={{ fontFamily: "var(--font-mono)", fontSize: 26 }}>{eventId}</h1>
          <p className="header-subtitle">
            Timestamped autonomous execution trail with model inferences and policy triggers
          </p>
        </div>
        <span className={`badge badge-lg ${statusClass}`}>
          {last.event_status_after.replace(/_/g, " ")}
        </span>
      </div>

      <div className="event-meta">
        <div className="event-meta-card">
          <span>Decline Code</span>
          <strong style={{ fontFamily: "var(--font-mono)", color: "#818cf8" }}>{first.decline_code}</strong>
        </div>
        <div className="event-meta-card">
          <span>Diagnosed Cause</span>
          <strong style={{ textTransform: "capitalize" }}>{first.cause_category.replace(/_/g, " ")}</strong>
        </div>
        <div className="event-meta-card">
          <span>Amount at Risk</span>
          <strong style={{ fontFamily: "var(--font-mono)" }}>{formatRupees(first.amount)}</strong>
        </div>
        <div className="event-meta-card">
          <span>Pipeline Steps</span>
          <strong style={{ fontFamily: "var(--font-mono)" }}>{steps.length} actions taken</strong>
        </div>
      </div>

      <div className="callout">
        <div className="callout-icon-title">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 2a8 8 0 0 0-8 8c0 3.3 2 6.1 5 7.4V20a1 1 0 0 0 1 1h4a1 1 0 0 0 1-1v-2.6c3-1.3 5-4.1 5-7.4a8 8 0 0 0-8-8z" />
            <line x1="9.5" y1="9" x2="10" y2="9" />
            <line x1="14" y1="9" x2="14.5" y2="9" />
          </svg>
          <span>Autonomous Diagnosis Rationale</span>
        </div>
        <p>{first.diagnosis_rationale}</p>
      </div>

      <h3 className="timeline-heading">Complete Step-by-Step Audit Trail</h3>
      <AuditTimeline steps={steps} />
    </div>
  );
}
