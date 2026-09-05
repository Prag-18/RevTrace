import type { AuditStep } from "../api/client";

export const ACTION_LABELS: Record<string, string> = {
  retry_immediate: "Retry Immediately",
  retry_delayed: "Retry (Delayed / Cooldown)",
  request_card_update: "Request Card Update via Email",
  escalate_alternate_payment: "Escalate — Offer Alternate Payment",
  escalate_human: "Escalate to Human Operations",
  hold: "Hold (Cooldown Active)",
  hold_closed_lost: "Close — Unrecovered (Exhausted)",
};

const CAUSE_LABELS: Record<string, string> = {
  insufficient_funds: "Insufficient Funds",
  expired_card: "Expired Card",
  data_entry_error: "Data Entry Error (CVV)",
  issuer_technical: "Issuer Technical Failure",
  issuer_risk_flag: "Issuer Risk Flag (Fraud/Decline)",
};

const CAUSE_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  insufficient_funds: { bg: "rgba(99, 102, 241, 0.15)", text: "#818cf8", border: "rgba(99, 102, 241, 0.3)" },
  expired_card: { bg: "rgba(245, 158, 11, 0.15)", text: "#fbbf24", border: "rgba(245, 158, 11, 0.3)" },
  data_entry_error: { bg: "rgba(168, 85, 247, 0.15)", text: "#c084fc", border: "rgba(168, 85, 247, 0.3)" },
  issuer_technical: { bg: "rgba(6, 182, 212, 0.15)", text: "#22d3ee", border: "rgba(6, 182, 212, 0.3)" },
  issuer_risk_flag: { bg: "rgba(244, 63, 94, 0.15)", text: "#fb7185", border: "rgba(244, 63, 94, 0.3)" },
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

/** Render policy rationale with visual decision flow chips instead of raw unformatted logs */
function DecisionRationaleView({ rationale }: { rationale: string }) {
  // Pattern 1: Cause '...', model-predicted recovery probability X -> action '...' per Y policy.
  const scoreMatch = rationale.match(
    /^Cause\s+'([^']+)',\s+model-predicted recovery probability\s+([\d\.]+)\s+->\s+action\s+'([^']+)'\s+per\s+([^\.]+)\s+policy\.?$/i
  );
  if (scoreMatch) {
    const [, cause, probStr, action, policy] = scoreMatch;
    const prob = Math.round(parseFloat(probStr) * 100);
    const causeStyle = CAUSE_COLORS[cause] || { bg: "rgba(255,255,255,0.06)", text: "#cbd5e1", border: "rgba(255,255,255,0.1)" };

    return (
      <div className="decision-flow-container">
        <div className="decision-flow-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="9 11 12 14 22 4" />
            <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
          </svg>
          <span>Autonomous Policy Evaluation</span>
        </div>
        <div className="decision-flow-grid">
          <div className="decision-node" style={{ background: causeStyle.bg, borderColor: causeStyle.border }}>
            <span className="decision-node-label">Diagnosed Cause</span>
            <strong className="decision-node-value" style={{ color: causeStyle.text }}>
              {CAUSE_LABELS[cause] || cause.replace(/_/g, " ")}
            </strong>
          </div>

          <div className="decision-connector">
            <span>+</span>
          </div>

          <div className="decision-node score-node">
            <span className="decision-node-label">ML Inferred Recovery</span>
            <strong className="decision-node-value" style={{ color: prob >= 60 ? "#34d399" : prob >= 30 ? "#fbbf24" : "#fb7185" }}>
              {prob}% Probability
            </strong>
          </div>

          <div className="decision-connector">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </div>

          <div className="decision-node action-node">
            <span className="decision-node-label">Triggered Action</span>
            <strong className="decision-node-value" style={{ color: "#ffffff" }}>
              {ACTION_LABELS[action] || action.replace(/_/g, " ")}
            </strong>
          </div>
        </div>
        <div className="decision-flow-footer">
          <span className="policy-rule-badge">Rule: {policy.replace(/_/g, " ")} policy</span>
        </div>
      </div>
    );
  }

  // Pattern 2: Cause '...' cannot be resolved... Forcing action '...' regardless of model score (X)
  const forcedMatch = rationale.match(
    /^Cause\s+'([^']+)'\s+cannot be resolved by retrying.*?Forcing action\s+'([^']+)'\s+regardless of model score\s*\(([\d\.]+)\)\.?$/i
  );
  if (forcedMatch) {
    const [, cause, action, probStr] = forcedMatch;
    const prob = Math.round(parseFloat(probStr) * 100);
    const causeStyle = CAUSE_COLORS[cause] || { bg: "rgba(245, 158, 11, 0.15)", text: "#fbbf24", border: "rgba(245, 158, 11, 0.3)" };

    return (
      <div className="decision-flow-container forced-rule">
        <div className="decision-flow-header">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>Forced Cause Rule (Deterministic Override)</span>
        </div>
        <div className="decision-flow-grid">
          <div className="decision-node" style={{ background: causeStyle.bg, borderColor: causeStyle.border }}>
            <span className="decision-node-label">Diagnosed Cause</span>
            <strong className="decision-node-value" style={{ color: causeStyle.text }}>
              {CAUSE_LABELS[cause] || cause.replace(/_/g, " ")}
            </strong>
          </div>

          <div className="decision-connector">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="5" y1="12" x2="19" y2="12" />
              <polyline points="12 5 19 12 12 19" />
            </svg>
          </div>

          <div className="decision-node action-node forced">
            <span className="decision-node-label">Forced Policy Intervention</span>
            <strong className="decision-node-value" style={{ color: "#fbbf24" }}>
              {ACTION_LABELS[action] || action.replace(/_/g, " ")}
            </strong>
          </div>
        </div>
        <div className="decision-flow-footer">
          <span className="policy-rule-badge warning">
            Bypasses raw ML prediction ({prob}%) — Retrying the same credentials cannot succeed
          </span>
        </div>
      </div>
    );
  }

  // Universal Fallback: Formatted text with code badges for quoted parameters
  const formattedParts = rationale.split(/('[\w_]+')/g).map((part, index) => {
    if (part.startsWith("'") && part.endsWith("'")) {
      const clean = part.slice(1, -1);
      return (
        <code key={index} className="inline-param-badge">
          {ACTION_LABELS[clean] || CAUSE_LABELS[clean] || clean.replace(/_/g, " ")}
        </code>
      );
    }
    return part;
  });

  return <p className="timeline-rationale">{formattedParts}</p>;
}

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

              {/* Enhanced Visual Decision Rationale */}
              <DecisionRationaleView rationale={s.policy_rationale} />

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
