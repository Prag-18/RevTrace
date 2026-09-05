import type { AuditStep } from "../api/client";

export const ACTION_LABELS: Record<string, string> = {
  retry_immediate: "Retry Immediately",
  retry_delayed: "Retry (Delayed / Cooldown)",
  request_card_update: "Request Card Update via Email",
  escalate_alternate_payment: "Escalate — Offer Alternate Payment (UPI/Netbanking)",
  escalate_human: "Escalate to Human Operations Review",
  hold: "Held (Cooldown / Attempt Limit)",
  hold_closed_lost: "Closed — Unrecovered (Exhausted)",
};

const getActionIcon = (action: string) => {
  if (action.includes("retry")) {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="23 4 23 10 17 10" />
        <polyline points="1 20 1 14 7 14" />
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
      </svg>
    );
  }
  if (action.includes("card_update") || action.includes("alternate_payment")) {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <line x1="2" y1="10" x2="22" y2="10" />
      </svg>
    );
  }
  if (action.includes("escalate")) {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
      </svg>
    );
  }
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
};

export default function AuditTimeline({ steps }: { steps: AuditStep[] }) {
  return (
    <div className="timeline">
      {steps.map((s) => {
        const prob = Math.round(s.recovery_probability * 100);
        return (
          <div key={s.step_number} className={`timeline-step ${s.blocked ? "step-blocked" : "step-active"}`}>
            <div className="timeline-marker">{s.step_number}</div>
            
            <div className="timeline-content">
              <div className="timeline-header">
                <div className="timeline-action-title">
                  {getActionIcon(s.policy_action)}
                  <span>{ACTION_LABELS[s.policy_action] || s.policy_action}</span>
                </div>
                <span className="timeline-timestamp">
                  {new Date(s.simulated_timestamp).toLocaleString("en-IN", {
                    dateStyle: "medium",
                    timeStyle: "short",
                  })}
                </span>
              </div>

              <div className="timeline-score-row">
                <span className="timeline-score-label">ML Recovery Probability:</span>
                <span className="timeline-score-badge">{prob}%</span>
                <div className="rate-bar-track" style={{ width: 100, height: 6 }}>
                  <div
                    className="rate-bar-fill"
                    style={{
                      width: `${prob}%`,
                      background: prob > 60 ? "linear-gradient(90deg, #10b981, #34d399)" : prob > 30 ? "linear-gradient(90deg, #f59e0b, #fbbf24)" : "linear-gradient(90deg, #f43f5e, #fb7185)",
                    }}
                  />
                </div>
              </div>

              <p className="timeline-rationale">{s.policy_rationale}</p>

              {s.blocked && s.block_reason && (
                <div className="block-tag">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
                  </svg>
                  <span>Policy Guardrail: {s.block_reason.replace(/_/g, " ")}</span>
                </div>
              )}

              {s.razorpay_payment_link_url && (
                <div className="link-tag">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
                    <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
                  </svg>
                  <span>Payment link created:</span>
                  <a href={s.razorpay_payment_link_url} target="_blank" rel="noreferrer">
                    {s.razorpay_payment_link_url}
                  </a>
                  {s.razorpay_mock && <span className="mock-tag">Test Mode</span>}
                </div>
              )}

              {s.outcome && (
                <div>
                  <span className={`outcome-tag ${s.outcome === "paid" ? "outcome-paid" : "outcome-not-paid"}`}>
                    {s.outcome === "paid" ? (
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                        Customer Outcome: Payment Successfully Recovered
                      </>
                    ) : (
                      <>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <line x1="18" y1="6" x2="6" y2="18" />
                          <line x1="6" y1="6" x2="18" y2="18" />
                        </svg>
                        Customer Outcome: Charge Attempt Unpaid
                      </>
                    )}
                  </span>
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
