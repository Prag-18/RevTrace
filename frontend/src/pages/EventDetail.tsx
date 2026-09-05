import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, type AuditStep } from "../api/client";

function formatRupees(n: number): string {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

const ACTION_LABELS: Record<string, string> = {
  retry_immediate: "Retry immediately",
  retry_delayed: "Retry (delayed)",
  request_card_update: "Request card update",
  escalate_alternate_payment: "Escalate — offer alternate payment",
  escalate_human: "Escalated to human review",
  hold: "Held (cooldown/limit)",
  hold_closed_lost: "Closed — unrecovered",
};

export default function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>();
  const [steps, setSteps] = useState<AuditStep[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!eventId) return;
    api.getEventAudit(eventId).then((d) => setSteps(d.steps)).catch((e) => setError(e.message));
  }, [eventId]);

  if (error) {
    return (
      <div className="empty-state">
        <p>Couldn't load audit trail: {error}</p>
        <Link to="/events">← Back to events</Link>
      </div>
    );
  }
  if (steps.length === 0) return <div className="empty-state">Loading…</div>;

  const first = steps[0];
  const last = steps[steps.length - 1];

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <Link to="/events" className="back-link">← Back to events</Link>
          <h1>{eventId}</h1>
        </div>
        <span className={`badge badge-lg ${
          last.event_status_after === "recovered" ? "badge-success" :
          last.event_status_after === "escalated" ? "badge-warning" : "badge-neutral"
        }`}>
          {last.event_status_after.replace(/_/g, " ")}
        </span>
      </div>

      <div className="event-meta">
        <div><span>Decline code</span><strong>{first.decline_code}</strong></div>
        <div><span>Cause</span><strong>{first.cause_category.replace(/_/g, " ")}</strong></div>
        <div><span>Amount</span><strong>{formatRupees(first.amount)}</strong></div>
        <div><span>Total steps</span><strong>{steps.length}</strong></div>
      </div>

      <div className="callout">{first.diagnosis_rationale}</div>

      <h3 className="timeline-heading">Audit trail</h3>
      <div className="timeline">
        {steps.map((s) => (
          <div key={s.step_number} className={`timeline-step ${s.blocked ? "step-blocked" : "step-active"}`}>
            <div className="timeline-marker">{s.step_number}</div>
            <div className="timeline-content">
              <div className="timeline-header">
                <strong>{ACTION_LABELS[s.policy_action] || s.policy_action}</strong>
                <span className="timeline-timestamp">
                  {new Date(s.simulated_timestamp).toLocaleString()}
                </span>
              </div>

              <div className="timeline-score">
                Model-predicted recovery probability: <strong>{(s.recovery_probability * 100).toFixed(0)}%</strong>
              </div>

              <p className="timeline-rationale">{s.policy_rationale}</p>

              {s.blocked && s.block_reason && (
                <div className="block-tag">Blocked: {s.block_reason.replace(/_/g, " ")}</div>
              )}

              {s.razorpay_payment_link_url && (
                <div className="link-tag">
                  Payment link created:{" "}
                  <a href={s.razorpay_payment_link_url} target="_blank" rel="noreferrer">
                    {s.razorpay_payment_link_url}
                  </a>{" "}
                  {s.razorpay_mock && <span className="mock-tag">mock</span>}
                </div>
              )}

              {s.outcome && (
                <div className={`outcome-tag ${s.outcome === "paid" ? "outcome-paid" : "outcome-not-paid"}`}>
                  Outcome: {s.outcome === "paid" ? "Payment received" : "Not paid"}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

