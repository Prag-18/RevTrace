import type { AuditStep } from "../api/client";

type Props = { steps: AuditStep[] };

/** Ordered detect → diagnose → act → stop audit trail for one event. */
export default function AuditTimeline({ steps }: Props) {
  return (
    <div className="timeline">
      {steps.map((step) => (
        <div key={step.step_number} className={`timeline-step ${step.blocked ? "step-blocked" : "step-active"}`}>
          <div className="timeline-marker">{step.step_number}</div>
          <div className="timeline-content">
            <div className="timeline-header">
              <strong>{step.policy_action.replace(/_/g, " ")}</strong>
              <span className="timeline-timestamp">{new Date(step.simulated_timestamp).toLocaleString()}</span>
            </div>
            <div className="timeline-score">Recovery probability: <strong>{(step.recovery_probability * 100).toFixed(0)}%</strong></div>
            <p className="timeline-rationale">{step.policy_rationale}</p>
            {step.blocked && step.block_reason && <div className="block-tag">Stopped: {step.block_reason.replace(/_/g, " ")}</div>}
            {step.outcome && <div className={`outcome-tag ${step.outcome === "paid" ? "outcome-paid" : "outcome-not-paid"}`}>Outcome: {step.outcome}</div>}
          </div>
        </div>
      ))}
    </div>
  );
}
