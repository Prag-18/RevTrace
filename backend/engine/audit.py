"""
Audit log writer.

Every StepResult produced by state_machine.py gets written here as one
row — this is the literal, inspectable audit trail the track's bar asks
for: what was detected, how it was diagnosed, what action was taken (or
why it was blocked), and what happened.

Two backends behind one interface, same pattern as executor.py:

  CSV BACKEND (default, no credentials needed):
    Appends rows to a local CSV file. Fully testable offline — used for
    all development/testing in this environment, since its network
    egress allowlist does not include Supabase.

  SUPABASE BACKEND (set AUDIT_BACKEND=supabase + credentials):
    Writes rows to a Supabase Postgres table via the REST API. Requires:
        SUPABASE_URL=https://xxxx.supabase.co
        SUPABASE_KEY=your_anon_or_service_key
    Run the accompanying supabase_schema.sql in the Supabase SQL editor
    first to create the audit_log table.
"""

import csv
import os
from dataclasses import asdict, fields
from datetime import datetime
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

AUDIT_BACKEND = os.environ.get("AUDIT_BACKEND", "csv").lower()

DEFAULT_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "audit_log.csv")


def _serialize_row(step_result) -> dict:
    """Convert a StepResult dataclass into a JSON/CSV-safe dict."""
    row = asdict(step_result)
    if isinstance(row.get("simulated_timestamp"), datetime):
        row["simulated_timestamp"] = row["simulated_timestamp"].isoformat()
    return row


class AuditLogger:
    def __init__(self, backend: Optional[str] = None, csv_path: str = DEFAULT_CSV_PATH):
        self.backend = (backend or AUDIT_BACKEND).lower()
        self.csv_path = csv_path

        if self.backend == "supabase":
            from supabase import create_client
            url = os.environ.get("SUPABASE_URL")
            # Accept the current Supabase variable names as well as the
            # original generic name for backwards compatibility.
            key = (os.environ.get("SUPABASE_SECRET_KEY")
                   or os.environ.get("SUPABASE_KEY")
                   or os.environ.get("SUPABASE_PUBLISHABLE_KEY"))
            if not url or not key:
                raise RuntimeError(
                    "AUDIT_BACKEND=supabase but SUPABASE_URL and a Supabase key are not set."
                )
            self.client = create_client(url, key)
        elif self.backend == "csv":
            self.client = None
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        else:
            raise ValueError(f"Unknown AUDIT_BACKEND '{self.backend}'; use 'csv' or 'supabase'.")

    # ------------------------------------------------------------------
    def log_step(self, step_result) -> None:
        """Write a single StepResult as one audit-log row."""
        row = _serialize_row(step_result)

        if self.backend == "supabase":
            self.client.table("audit_log").insert(row).execute()
        else:
            self._append_csv_row(row)

    def log_steps(self, step_results: List) -> None:
        for r in step_results:
            self.log_step(r)

    # ------------------------------------------------------------------
    def _append_csv_row(self, row: dict) -> None:
        file_exists = os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)

    # ------------------------------------------------------------------
    def read_all(self):
        """Read the full audit log back (CSV backend only — used by the
        dashboard/API layer and by tests). Supabase reads should go
        through the FastAPI layer's own client instead.
        """
        import pandas as pd
        if self.backend != "csv":
            raise NotImplementedError("read_all() is only implemented for the CSV backend.")
        if not os.path.exists(self.csv_path):
            return pd.DataFrame()
        return pd.read_csv(self.csv_path)

    def clear(self) -> None:
        """Remove all existing audit rows — used to reset between batch runs."""
        if self.backend == "csv":
            if os.path.exists(self.csv_path):
                os.remove(self.csv_path)
        else:
            # supabase: delete all rows (be careful — irreversible)
            self.client.table("audit_log").delete().neq("event_id", "__never_matches__").execute()


if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(__file__))
    from state_machine import EventLifecycle
    from policy import PolicyEngine
    from executor import RazorpayExecutor
    import pandas as pd

    print(f"AuditLogger running with backend='{AUDIT_BACKEND}'\n")

    events_path = os.path.join(os.path.dirname(__file__), "..", "data", "events.csv")
    df = pd.read_csv(events_path)
    event = df[df["decline_code"] == "card_expired"].iloc[0].to_dict()

    policy_engine = PolicyEngine()
    executor = RazorpayExecutor()
    lifecycle = EventLifecycle(event, policy_engine, executor)
    history = lifecycle.run_to_completion()

    logger = AuditLogger()
    # A local demo run is reproducible after clearing its CSV. Never erase a
    # shared Supabase audit table merely because this script was executed.
    if logger.backend == "csv":
        logger.clear()
    logger.log_steps(history)

    print(f"Wrote {len(history)} audit rows for event {event['event_id']}")
    if logger.backend == "csv":
        result_df = logger.read_all()
        print(f"\nRead back {len(result_df)} rows from {logger.csv_path}:")
        print(result_df[["event_id", "step_number", "policy_action", "blocked", "outcome"]].to_string(index=False))
