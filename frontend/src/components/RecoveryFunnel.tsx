import type { BatchSummary } from "../api/client";

type Props = { summary: BatchSummary };

/** Compact status funnel for the current recovery batch. */
export default function RecoveryFunnel({ summary }: Props) {
  const stages = ["recovered", "escalated", "closed_lost"] as const;
  const total = summary.n_events || 1;

  return (
    <section className="chart-card">
      <h3>Recovery funnel</h3>
      <div className="stat-grid">
        {stages.map((stage) => {
          const count = summary.status_counts[stage] ?? 0;
          return (
            <div className="stat-card" key={stage}>
              <div className="stat-label">{stage.replace(/_/g, " ")}</div>
              <div className="stat-value">{count}</div>
              <div className="stat-sub">{((count / total) * 100).toFixed(1)}% of events</div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
