"""
Event lifecycle state machine.

Tracks ONE event's recovery journey across multiple attempts, using a
SIMULATED clock rather than real wall-clock time. This lets Day 5's batch
run compress what would be a multi-week recovery window (24h cooldowns,
12-day windows, etc.) into an instant run, while still exercising the
exact same cooldown/cap logic in policy.py — we simply pass a future
`current_time` into policy.decide() instead of waiting for real time to pass.

Each call to `.step()` represents one full decision cycle: advance the
simulated clock, ask the policy engine what to do, execute it if allowed,
simulate the customer's response (for backtesting only), and record
everything. The loop naturally terminates when the event is RECOVERED,
ESCALATED, or CLOSED_LOST.
"""

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

sys.path.append(os.path.dirname(__file__))
from diagnosis import diagnose
from policy import PolicyEngine, AttemptState, PolicyDecision
from executor import RazorpayExecutor, synthetic_indian_mobile


# For backtest-outcome simulation only: which actions are PLAUSIBLE for a
# given cause_category, not just the single fixed label produced by the
# Day-1 generator. The generator's ground_truth_best_action picks one
# canonical action per decline_code (e.g. insufficient_funds -> always
# "retry_delayed"), but the actual policy is score-driven and can
# correctly choose retry_immediate for a high-confidence insufficient_
# funds case, or retry_delayed for a borderline issuer_technical case —
# both are legitimate, cause-appropriate choices. Comparing against a
# single rigid label would unfairly penalize good dynamic decisions.
# Only genuinely nonsensical combinations (e.g. asking for a card update
# on a transient issuer-technical glitch) count as a real mismatch.
PLAUSIBLE_ACTIONS_BY_CAUSE = {
    "insufficient_funds": {"retry_immediate", "retry_delayed"},
    "expired_card": {"request_card_update"},
    "data_entry_error": {"request_card_update"},
    "issuer_technical": {"retry_immediate", "retry_delayed"},
    "issuer_risk_flag": {"escalate_alternate_payment"},
}


class EventStatus(Enum):
    OPEN = "open"                   # still being actively worked
    RECOVERED = "recovered"         # payment succeeded
    ESCALATED = "escalated"         # handed to a human, agent stops acting
    CLOSED_LOST = "closed_lost"     # max attempts / window exhausted, unrecovered


@dataclass
class StepResult:
    """One row of what happened during a single step() call — this IS
    the shape of one audit-log entry."""
    event_id: str
    step_number: int
    simulated_timestamp: datetime
    decline_code: str
    cause_category: str
    diagnosis_rationale: str
    recovery_probability: float
    attempt_count_before: int
    policy_action: str
    policy_rationale: str
    blocked: bool
    block_reason: Optional[str]
    razorpay_success: Optional[bool]
    razorpay_payment_link_id: Optional[str]
    razorpay_payment_link_url: Optional[str]
    razorpay_mock: Optional[bool]
    outcome: Optional[str]          # "paid" / "not_paid" / None (no customer-facing action taken)
    event_status_after: str
    amount: float


class EventLifecycle:
    """Drives one event through repeated policy decisions on a simulated
    clock until it reaches a terminal state (RECOVERED / ESCALATED /
    CLOSED_LOST) or hits a safety cap on the number of steps.
    """

    # Hard safety valve — independent of policy's own attempt cap — so a
    # misconfigured policy can never cause an infinite loop in the runner.
    MAX_STEPS = 10

    def __init__(self, event: dict, policy_engine: PolicyEngine,
                 executor: RazorpayExecutor, rng=None,
                 backtest_mode: bool = True):
        self.event = event
        self.policy_engine = policy_engine
        self.executor = executor
        self.rng = rng
        self.backtest_mode = backtest_mode  # if True, simulate customer outcome for demo metrics

        self.cause_info = diagnose(event["decline_code"])
        self.status = EventStatus.OPEN
        self.state = AttemptState(
            attempt_count=0,
            last_action_at=None,
            first_detected_at=datetime.fromisoformat(event["timestamp"]).replace(tzinfo=timezone.utc),
        )
        self.simulated_now = self.state.first_detected_at
        self.history: List[StepResult] = []

    def _score(self) -> float:
        # imported lazily to avoid a hard dependency at module import time
        # if this file is used somewhere the model isn't needed
        from run_single_event import score_event, load_model_bundle
        model, scaler, feature_columns = load_model_bundle()
        return score_event(model, scaler, feature_columns, self.event, self.cause_info.cause_category)

    def step(self) -> StepResult:
        """Advance the event by exactly one decision cycle."""
        step_number = len(self.history) + 1
        recovery_probability = self._score()

        decision = self.policy_engine.decide(
            cause_category=self.cause_info.cause_category,
            recovery_probability=recovery_probability,
            state=self.state,
            event_amount=self.event["amount"],
            current_time=self.simulated_now,
        )

        result = StepResult(
            event_id=self.event["event_id"],
            step_number=step_number,
            simulated_timestamp=self.simulated_now,
            decline_code=self.event["decline_code"],
            cause_category=self.cause_info.cause_category,
            diagnosis_rationale=self.cause_info.rationale,
            recovery_probability=round(recovery_probability, 4),
            attempt_count_before=self.state.attempt_count,
            policy_action=decision.action,
            policy_rationale=decision.rationale,
            blocked=decision.blocked,
            block_reason=decision.block_reason,
            razorpay_success=None,
            razorpay_payment_link_id=None,
            razorpay_payment_link_url=None,
            razorpay_mock=None,
            outcome=None,
            event_status_after=self.status.value,
            amount=self.event["amount"],
        )

        executable_actions = {"retry_immediate", "retry_delayed",
                               "request_card_update", "escalate_alternate_payment"}

        if decision.action in executable_actions:
            exec_result = self.executor.create_payment_link(
                event_id=f"{self.event['event_id']}_step{step_number}",
                amount_rupees=self.event["amount"],
                customer_name=self.event.get("customer_id", "customer"),
                customer_contact=synthetic_indian_mobile(self.event.get("customer_id", self.event["event_id"])),
                description=f"Payment recovery: {decision.action} ({self.cause_info.cause_category})",
                action_type=decision.action,
            )
            result.razorpay_success = exec_result.success
            result.razorpay_payment_link_id = exec_result.payment_link_id
            result.razorpay_payment_link_url = exec_result.payment_link_url
            result.razorpay_mock = exec_result.mock

            # advance attempt state
            self.state.attempt_count += 1
            self.state.last_action_at = self.simulated_now

            if self.backtest_mode:
                plausible = PLAUSIBLE_ACTIONS_BY_CAUSE.get(self.cause_info.cause_category, set())
                is_correct_action = decision.action in plausible
                paid = RazorpayExecutor.simulate_customer_outcome(
                    self.event.get("ground_truth_recoverable", False), decision.action,
                    is_correct_action=is_correct_action, rng=self.rng
                )
                result.outcome = "paid" if paid else "not_paid"
                if paid:
                    self.status = EventStatus.RECOVERED

            # advance the simulated clock so the NEXT step naturally clears
            # this action's cooldown, rather than looping on the same hour
            notify_delay = decision.notify_delay_hours or 0
            cause_cooldown = self.policy_engine.policy["cause_rules"].get(
                self.cause_info.cause_category, {}
            ).get("cooldown_hours", 24)
            jump_hours = max(notify_delay, cause_cooldown, 1)
            self.simulated_now += timedelta(hours=jump_hours)

        elif decision.action == "escalate_human":
            self.status = EventStatus.ESCALATED

        elif decision.action == "hold_closed_lost":
            self.status = EventStatus.CLOSED_LOST

        elif decision.action == "hold":
            # blocked by cooldown/window — jump the clock forward to the
            # earliest time the block would clear, rather than spinning
            self.simulated_now += timedelta(hours=6)

        result.event_status_after = self.status.value
        self.history.append(result)
        return result

    def run_to_completion(self) -> List[StepResult]:
        """Repeatedly step() until the event reaches a terminal status or
        hits the safety cap on steps.
        """
        while self.status == EventStatus.OPEN and len(self.history) < self.MAX_STEPS:
            self.step()
        return self.history


if __name__ == "__main__":
    import pandas as pd

    events_path = os.path.join(os.path.dirname(__file__), "..", "data", "events.csv")
    df = pd.read_csv(events_path)

    policy_engine = PolicyEngine()
    executor = RazorpayExecutor()  # respects RAZORPAY_MODE from .env — mock by default here

    # run one full lifecycle for one event of each interesting kind
    sample = pd.concat([
        df[df["decline_code"] == "insufficient_funds"].head(1),
        df[df["decline_code"] == "card_expired"].head(1),
        df[df["decline_code"] == "fraud_suspected_by_issuer"].head(1),
    ])

    for _, row in sample.iterrows():
        event = row.to_dict()
        lifecycle = EventLifecycle(event, policy_engine, executor)
        history = lifecycle.run_to_completion()

        print(f"\n{'='*78}")
        print(f"Event {event['event_id']}  ({event['decline_code']})  "
              f"final_status={lifecycle.status.value}")
        for r in history:
            print(f"  step {r.step_number}: t+{(r.simulated_timestamp - lifecycle.state.first_detected_at)} "
                  f"-> {r.policy_action:22s} blocked={r.blocked}  outcome={r.outcome}")