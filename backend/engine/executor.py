"""
Razorpay execution layer.

Every recovery action that touches money or the customer goes through
this module, and every call here is logged by the caller into the audit
trail. This module has two modes:

  MOCK MODE (default, no credentials needed):
    Returns realistic, deterministic fake Razorpay responses. This lets
    the full pipeline be built, tested, and demoed without live network
    access or real credentials — useful here since this environment's
    egress allowlist does not include api.razorpay.com.

  LIVE MODE (set RAZORPAY_MODE=live + real test-mode credentials):
    Makes real calls to the Razorpay Test Mode API using the official
    razorpay Python SDK. Requires:
        RAZORPAY_KEY_ID=rzp_test_...
        RAZORPAY_KEY_SECRET=...
    Test-mode keys never move real money — safe to use during development
    and for the hackathon demo.

Both modes implement the exact same interface, so the policy/orchestration
layer never needs to know which mode it's running in.
"""

import hashlib
import os
import random
import time
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

# Loads variables from a .env file in the current working directory (or any
# parent directory) into os.environ, if one exists. Safe to call even if
# no .env file is present — it just does nothing in that case.
load_dotenv()

MOCK_MODE = os.environ.get("RAZORPAY_MODE", "mock").lower() != "live"


def synthetic_indian_mobile(seed_str: str) -> str:
    """Deterministically generate a plausible-looking Indian mobile number
    from a seed string (e.g. customer_id), avoiding patterns Razorpay's
    validation rejects (e.g. long runs of the same repeated digit — the
    placeholder +919999999999 used earlier triggers 'Recurring digits in
    customer contact are disallowed').
    """
    h = hashlib.sha256(seed_str.encode()).hexdigest()
    digits = [str(int(c, 16) % 10) for c in h]

    # Indian mobile numbers start with 6-9
    first = str(6 + (int(h[0], 16) % 4))
    number = [first]

    for d in digits[1:]:
        # avoid 3+ identical digits in a row, which trips the recurring-digit check
        if len(number) >= 2 and number[-1] == number[-2] == d:
            d = str((int(d) + 1) % 10)
        number.append(d)
        if len(number) == 10:
            break

    return "+91" + "".join(number)


@dataclass
class RazorpayActionResult:
    success: bool
    payment_link_id: Optional[str]
    payment_link_url: Optional[str]
    status: str                 # created / failed / error
    raw_response: dict
    mock: bool = MOCK_MODE


class RazorpayExecutor:
    def __init__(self):
        self.mock = MOCK_MODE
        if not self.mock:
            import razorpay  # imported lazily so mock mode has zero dependency risk
            key_id = os.environ.get("RAZORPAY_KEY_ID")
            key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
            if not key_id or not key_secret:
                raise RuntimeError(
                    "RAZORPAY_MODE=live but RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET "
                    "are not set. Set both env vars to Razorpay TEST MODE credentials."
                )
            self.client = razorpay.Client(auth=(key_id, key_secret))
        else:
            self.client = None

    # ------------------------------------------------------------------
    # Core action: create a payment link.
    # This is the single primitive every recovery action uses — the
    # difference between retry_immediate / retry_delayed / request_card_
    # update / escalate_alternate_payment is only in the description,
    # notify timing, and (for card update) the payment methods enabled —
    # not in a different API call.
    # ------------------------------------------------------------------
    def create_payment_link(self, event_id: str, amount_rupees: float,
                             customer_name: str, customer_contact: str,
                             description: str, action_type: str) -> RazorpayActionResult:
        amount_paise = int(round(amount_rupees * 100))

        if self.mock:
            return self._mock_create_payment_link(
                event_id, amount_paise, customer_name, description, action_type
            )

        try:
            payload = {
                "amount": amount_paise,
                "currency": "INR",
                "description": description,
                "customer": {
                    "name": customer_name,
                    "contact": customer_contact,
                },
                "notify": {"sms": True, "email": True},
                "reminder_enable": True,
                "notes": {
                    "event_id": event_id,
                    "action_type": action_type,
                    "source": "ai_revenue_recovery_agent",
                },
            }
            response = self.client.payment_link.create(payload)
            return RazorpayActionResult(
                success=True,
                payment_link_id=response.get("id"),
                payment_link_url=response.get("short_url"),
                status=response.get("status", "created"),
                raw_response=response,
                mock=False,
            )
        except Exception as e:
            return RazorpayActionResult(
                success=False,
                payment_link_id=None,
                payment_link_url=None,
                status="error",
                raw_response={"error": str(e)},
                mock=False,
            )

    # ------------------------------------------------------------------
    # Mock implementation
    # ------------------------------------------------------------------
    def _mock_create_payment_link(self, event_id, amount_paise, customer_name,
                                   description, action_type) -> RazorpayActionResult:
        # deterministic fake ID from event_id + action_type, so re-running
        # the same scenario in mock mode is reproducible
        seed_str = f"{event_id}:{action_type}:{amount_paise}"
        fake_hash = hashlib.sha256(seed_str.encode()).hexdigest()[:14]
        link_id = f"plink_MOCK{fake_hash}"
        fake_url = f"https://rzp.io/i/mock_{fake_hash[:8]}"

        return RazorpayActionResult(
            success=True,
            payment_link_id=link_id,
            payment_link_url=fake_url,
            status="created",
            raw_response={
                "id": link_id,
                "short_url": fake_url,
                "amount": amount_paise,
                "currency": "INR",
                "description": description,
                "status": "created",
                "customer": {"name": customer_name},
                "notes": {"event_id": event_id, "action_type": action_type},
                "_mock": True,
            },
            mock=True,
        )

    # ------------------------------------------------------------------
    # Simulated OUTCOME of a sent payment link, for batch backtesting.
    # In a real deployment this would come from a Razorpay webhook
    # (payment_link.paid / payment_link.expired) days or hours later.
    # For the hackathon batch run, we simulate the outcome using the
    # event's ground-truth recoverability so we can compute a real
    # "revenue recovered" number without waiting on real customers.
    # THIS FUNCTION IS ONLY USED IN THE BACKTEST/DEMO BATCH RUNNER,
    # NEVER IN THE LIVE POLICY/DIAGNOSIS PATH.
    # ------------------------------------------------------------------
    @staticmethod
    def simulate_customer_outcome(ground_truth_recoverable: bool, action_type: str,
                                   rng: Optional[random.Random] = None) -> bool:
        rng = rng or random
        # forced_action outcomes (request_card_update) succeed a bit less
        # often than a well-timed retry even when the underlying event was
        # "recoverable", to reflect real friction in asking the customer
        # to take an action vs. an automated retry succeeding on its own.
        friction = {
            "retry_immediate": 0.95,
            "retry_delayed": 0.90,
            "request_card_update": 0.75,
            "escalate_alternate_payment": 0.65,
        }.get(action_type, 0.8)
        if not ground_truth_recoverable:
            return False
        return rng.random() < friction


if __name__ == "__main__":
    print(f"RazorpayExecutor running in {'MOCK' if MOCK_MODE else 'LIVE'} mode\n")
    executor = RazorpayExecutor()
    result = executor.create_payment_link(
        event_id="evt_test123",
        amount_rupees=499.00,
        customer_name="Test Customer",
        customer_contact=synthetic_indian_mobile("evt_test123"),
        description="Payment retry for your recent subscription renewal",
        action_type="retry_immediate",
    )
    print(f"success={result.success}")
    print(f"payment_link_id={result.payment_link_id}")
    print(f"payment_link_url={result.payment_link_url}")
    print(f"status={result.status}")
    print(f"mock={result.mock}")
    if not result.success:
        print(f"\nERROR DETAILS: {result.raw_response}")