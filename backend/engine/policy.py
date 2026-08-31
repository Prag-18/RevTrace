"""
Policy engine.

Given a diagnosed cause, a model recovery-probability score, and the
event's current attempt state, decides ONE bounded action — or decides
to escalate to a human, or to close the event as unrecovered.

Every decision returns a full, human-readable rationale so the caller
can write a complete audit-trail row without re-deriving the logic.

This module NEVER calls Razorpay or does any I/O — it is pure decision
logic, which makes it trivially unit-testable in isolation from the
payment integration.
"""

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import yaml

POLICY_PATH = os.path.join(os.path.dirname(__file__), "..", "policy.yaml")


@dataclass
class AttemptState:
    """Mutable state tracked per event across the recovery window."""
    attempt_count: int = 0
    last_action_at: Optional[datetime] = None
    first_detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PolicyDecision:
    action: str
    rationale: str
    blocked: bool = False           # True if a hard limit prevented action
    block_reason: Optional[str] = None
    notify_delay_hours: Optional[float] = None


class PolicyEngine:
    def __init__(self, policy_path: str = POLICY_PATH):
        with open(policy_path, "r") as f:
            self.policy = yaml.safe_load(f)

    # -- helpers -------------------------------------------------------

    def _select_action_by_score(self, score: float) -> str:
        for tier in self.policy["score_thresholds"]:
            if score >= tier["min_score"]:
                return tier["action"]
        # score_thresholds always includes a min_score: 0.0 catch-all,
        # so this line should be unreachable, but fail safe rather than
        # silently returning None.
        return "request_card_update"

    def _hours_since(self, ts: Optional[datetime]) -> float:
        if ts is None:
            return float("inf")
        return (datetime.now(timezone.utc) - ts).total_seconds() / 3600.0

    # -- main entry point ------------------------------------------------

    def decide(self, cause_category: str, recovery_probability: float,
               state: AttemptState, event_amount: float) -> PolicyDecision:
        limits = self.policy["global_limits"]
        cause_rule = self.policy["cause_rules"].get(cause_category)

        if cause_rule is None:
            return PolicyDecision(
                action="escalate_human",
                rationale=f"Unknown cause_category '{cause_category}' has no policy rule defined; "
                          f"routing to human review rather than guessing.",
                blocked=True,
                block_reason="no_policy_rule",
            )

        # --- Hard cap: total recovery window exceeded ---
        days_open = self._hours_since(state.first_detected_at) / 24.0
        if days_open > limits["max_total_recovery_window_days"]:
            return PolicyDecision(
                action="hold_closed_lost",
                rationale=f"Recovery window of {limits['max_total_recovery_window_days']} days exceeded "
                          f"({days_open:.1f} days open). Closing as unrecovered rather than continuing "
                          f"indefinitely.",
                blocked=True,
                block_reason="recovery_window_exceeded",
            )

        # --- Hard cap: max attempts reached ---
        if state.attempt_count >= limits["max_attempts_per_event"]:
            return PolicyDecision(
                action="escalate_human",
                rationale=f"Maximum of {limits['max_attempts_per_event']} automated attempts reached "
                          f"({state.attempt_count} used). Stopping automated action and routing to "
                          f"human recovery queue rather than continuing to contact the customer.",
                blocked=True,
                block_reason="max_attempts_reached",
            )

        # --- Hard cap: cooldown not yet elapsed ---
        hours_since_last = self._hours_since(state.last_action_at)
        min_cooldown = limits["min_cooldown_hours_between_attempts"]
        if hours_since_last < min_cooldown:
            return PolicyDecision(
                action="hold_closed_lost" if False else "hold",
                rationale=f"Only {hours_since_last:.1f}h since last action; global minimum cooldown is "
                          f"{min_cooldown}h. Holding to avoid contacting the customer too frequently.",
                blocked=True,
                block_reason="cooldown_not_elapsed",
            )

        # --- Compliance-sensitive causes: never auto-act ---
        if cause_rule.get("never_auto_action"):
            return PolicyDecision(
                action="escalate_human",
                rationale=cause_rule.get(
                    "escalation_reason",
                    f"Cause '{cause_category}' is configured as never_auto_action; routing to human review."
                ).strip(),
                blocked=True,
                block_reason="compliance_never_auto_action",
            )

        # --- Cause-specific cooldown (in addition to the global minimum) ---
        cause_cooldown = cause_rule.get("cooldown_hours", min_cooldown)
        if state.attempt_count > 0 and hours_since_last < cause_cooldown:
            return PolicyDecision(
                action="hold",
                rationale=f"Cause '{cause_category}' requires a {cause_cooldown}h cooldown between "
                          f"attempts (only {hours_since_last:.1f}h elapsed). Holding.",
                blocked=True,
                block_reason="cause_cooldown_not_elapsed",
            )

        # --- Forced action (e.g. expired card can never succeed on bare retry) ---
        if "forced_action" in cause_rule:
            action = cause_rule["forced_action"]
            rationale = (
                f"Cause '{cause_category}' cannot be resolved by retrying the same payment method. "
                f"Forcing action '{action}' regardless of model score ({recovery_probability:.2f})."
            )
        else:
            action = self._select_action_by_score(recovery_probability)
            rationale = (
                f"Cause '{cause_category}', model-predicted recovery probability "
                f"{recovery_probability:.2f} -> action '{action}' per score_thresholds policy."
            )

        action_config = self.policy["actions"].get(action, {})
        notify_delay = action_config.get("notify_delay_hours")
        if notify_delay == "cause_cooldown":
            notify_delay = cause_cooldown

        return PolicyDecision(
            action=action,
            rationale=rationale,
            blocked=False,
            notify_delay_hours=notify_delay,
        )


if __name__ == "__main__":
    engine = PolicyEngine()

    # quick smoke test across a few scenarios
    scenarios = [
        ("insufficient_funds", 0.72, AttemptState()),
        ("insufficient_funds", 0.20, AttemptState()),
        ("expired_card", 0.65, AttemptState()),
        ("issuer_risk_flag", 0.50, AttemptState()),
        ("issuer_technical", 0.80, AttemptState(attempt_count=3)),
    ]
    for cause, score, state in scenarios:
        decision = engine.decide(cause, score, state, event_amount=1000)
        print(f"[{cause:20s} score={score:.2f} attempts={state.attempt_count}] "
              f"-> {decision.action:25s} blocked={decision.blocked}")
        print(f"    {decision.rationale}\n")