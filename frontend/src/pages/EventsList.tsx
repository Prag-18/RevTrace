import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type EventSummary } from "../api/client";

const STATUS_BADGE: Record<string, string> = {
  recovered: "badge-success",
  escalated: "badge-warning",
  closed_lost: "badge-danger",
  open: "badge-neutral",
};

function formatRupees(n: number): string {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export default function EventsList() {
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  useEffect(() => {
    api.getBatchEvents().then((d) => setEvents(d.events)).catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="empty-state">
        <p>Couldn't load events: {error}</p>
        <p className="hint">Have you run <code>python run_batch.py</code> yet?</p>
      </div>
    );
  }

  const filtered = events
    .filter((e) => filter === "all" || e.final_status === filter)
    .filter((e) => e.event_id.toLowerCase().includes(search.toLowerCase()));

  return (
    <div className="page">
      <div className="page-header">
        <h1>Events ({events.length})</h1>
      </div>

      <div className="toolbar">
        <input
          className="search-input"
          placeholder="Search by event ID…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <div className="filter-pills">
          {["all", "recovered", "escalated", "closed_lost"].map((f) => (
            <button
              key={f}
              className={`pill ${filter === f ? "pill-active" : ""}`}
              onClick={() => setFilter(f)}
            >
              {f.replace(/_/g, " ")}
            </button>
          ))}
        </div>
      </div>

      <table className="data-table">
        <thead>
          <tr>
            <th>Event ID</th>
            <th>Decline code</th>
            <th>Cause</th>
            <th>Amount</th>
            <th>Attempts</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {filtered.slice(0, 100).map((e) => (
            <tr key={e.event_id}>
              <td>
                <Link to={`/events/${e.event_id}`} className="event-link">
                  {e.event_id}
                </Link>
              </td>
              <td>{e.decline_code}</td>
              <td>{e.cause_category.replace(/_/g, " ")}</td>
              <td>{formatRupees(e.amount)}</td>
              <td>{e.attempt_count_before}</td>
              <td>
                <span className={`badge ${STATUS_BADGE[e.final_status] || "badge-neutral"}`}>
                  {e.final_status.replace(/_/g, " ")}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {filtered.length > 100 && (
        <p className="hint">Showing first 100 of {filtered.length} matching events.</p>
      )}
    </div>
  );
}

