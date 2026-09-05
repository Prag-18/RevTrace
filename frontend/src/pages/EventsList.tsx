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
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");

  const load = () => {
    setLoading(true);
    api.getBatchEvents()
      .then((d) => setEvents(d.events))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  if (error) {
    return (
      <div className="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#f43f5e" strokeWidth="2">
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
        </svg>
        <p style={{ fontWeight: 700, color: "#fff" }}>Unable to load events</p>
        <p className="hint">{error}</p>
        <button className="btn-secondary" onClick={load}>Retry</button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="empty-state">
        <div className="spinner"></div>
        <p>Loading audit log events...</p>
      </div>
    );
  }

  const statusCounts = events.reduce((acc, e) => {
    acc[e.final_status] = (acc[e.final_status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const filtered = events
    .filter((e) => filter === "all" || e.final_status === filter)
    .filter((e) =>
      e.event_id.toLowerCase().includes(search.toLowerCase()) ||
      e.decline_code.toLowerCase().includes(search.toLowerCase()) ||
      e.cause_category.toLowerCase().includes(search.toLowerCase())
    );

  const filters = [
    { key: "all", label: "All", count: events.length },
    { key: "recovered", label: "Recovered", count: statusCounts["recovered"] || 0 },
    { key: "escalated", label: "Escalated", count: statusCounts["escalated"] || 0 },
    { key: "closed_lost", label: "Closed Lost", count: statusCounts["closed_lost"] || 0 },
  ];

  return (
    <div className="page">
      <div className="page-header">
        <div className="header-title-group">
          <h1>Events Audit Log</h1>
          <p className="header-subtitle">
            Search and inspect complete decision trails across all {events.length} batch events
          </p>
        </div>
      </div>

      <div className="toolbar">
        <div className="search-wrapper">
          <svg className="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            className="search-input"
            placeholder="Search by ID, decline code, or cause…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        <div className="filter-pills">
          {filters.map((f) => (
            <button
              key={f.key}
              className={`pill ${filter === f.key ? "pill-active" : ""}`}
              onClick={() => setFilter(f.key)}
            >
              <span>{f.label}</span>
              <span style={{ opacity: 0.7, marginLeft: 6, fontSize: 11 }}>({f.count})</span>
            </button>
          ))}
        </div>
      </div>

      <div className="chart-card" style={{ padding: 0, overflow: "hidden" }}>
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Decline Code</th>
                <th>Diagnosed Cause</th>
                <th>Amount</th>
                <th>Total Attempts</th>
                <th>Lifecycle Status</th>
                <th>Action</th>
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
                  <td>
                    <code style={{ fontSize: 12, color: "var(--text-secondary)", background: "rgba(255,255,255,0.04)", padding: "2px 6px", borderRadius: 4 }}>
                      {e.decline_code}
                    </code>
                  </td>
                  <td>
                    <span style={{ textTransform: "capitalize", fontWeight: 600 }}>
                      {e.cause_category.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                    {formatRupees(e.amount)}
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)" }}>
                    <span className="badge badge-neutral">{e.attempt_count_before}</span>
                  </td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[e.final_status] || "badge-neutral"}`}>
                      {e.final_status.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td>
                    <Link to={`/events/${e.event_id}`} className="btn-secondary" style={{ padding: "5px 12px", textDecoration: "none", fontSize: 12 }}>
                      Inspect →
                    </Link>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: "40px 20px", color: "var(--text-muted)" }}>
                    No events matched your search criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {filtered.length > 100 && (
        <p className="hint" style={{ marginTop: 14 }}>
          Showing first 100 of {filtered.length} matching events.
        </p>
      )}
    </div>
  );
}
