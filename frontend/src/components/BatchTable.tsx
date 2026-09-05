import { Link } from "react-router-dom";
import type { EventSummary } from "../api/client";

type Props = { events: EventSummary[] };

/** Drill-down table shared by batch-oriented views. */
export default function BatchTable({ events }: Props) {
  return (
    <table className="data-table">
      <thead><tr><th>Event ID</th><th>Cause</th><th>Amount</th><th>Attempts</th><th>Status</th></tr></thead>
      <tbody>{events.map((event) => (
        <tr key={event.event_id}>
          <td><Link className="event-link" to={`/events/${event.event_id}`}>{event.event_id}</Link></td>
          <td>{event.cause_category.replace(/_/g, " ")}</td>
          <td>₹{event.amount.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</td>
          <td>{event.attempt_count_before}</td>
          <td><span className="badge badge-neutral">{event.final_status.replace(/_/g, " ")}</span></td>
        </tr>
      ))}</tbody>
    </table>
  );
}
