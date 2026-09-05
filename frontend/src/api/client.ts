const API_BASE = "http://127.0.0.1:8000";

export interface CauseStats {
  n_events: number;
  amount_at_risk: number;
  amount_recovered: number;
  recovery_rate: number;
}

export interface BatchSummary {
  n_events: number;
  total_revenue_at_risk: number;
  total_revenue_recovered: number;
  overall_recovery_rate: number;
  baseline_recoverable_revenue_no_intervention: number;
  capture_rate_of_recoverable_revenue: number;
  status_counts: Record<string, number>;
  recovered_count: number;
  escalated_count: number;
  closed_lost_count: number;
  avg_attempts_per_event: number;
  by_cause_category: Record<string, CauseStats>;
}

export interface EventSummary {
  event_id: string;
  decline_code: string;
  cause_category: string;
  amount: number;
  final_status: string;
  attempt_count_before: number;
  outcome: string | null;
}

export interface AuditStep {
  event_id: string;
  step_number: number;
  simulated_timestamp: string;
  decline_code: string;
  cause_category: string;
  diagnosis_rationale: string;
  recovery_probability: number;
  attempt_count_before: number;
  policy_action: string;
  policy_rationale: string;
  blocked: boolean;
  block_reason: string | null;
  razorpay_success: boolean | null;
  razorpay_payment_link_id: string | null;
  razorpay_payment_link_url: string | null;
  razorpay_mock: boolean | null;
  outcome: string | null;
  event_status_after: string;
  amount: number;
}

export interface ModelMetricsEntry {
  auc: number;
  average_precision: number;
  brier_score: number;
  precision_at_0_5?: number;
  recall_at_0_5?: number;
  f1_at_0_5?: number;
  cv_auc_mean: number;
  cv_auc_std: number;
  cv_auc_folds: number[];
  n_test: number;
  n_train: number;
  confusion_matrix: number[][];
}

export interface FeatureImportance {
  feature: string;
  importance: number;
}

export interface ModelMetrics {
  production_model: string;
  gradient_boosting: ModelMetricsEntry;
  logistic_regression: ModelMetricsEntry;
  precision_recall_curve: { threshold: number; precision: number; recall: number }[];
  feature_importance: FeatureImportance[];
}

export interface SimulateRequest {
  decline_code: string;
  amount: number;
  event_type?: string;
  customer_tenure_days?: number;
  customer_past_success_rate?: number;
  customer_prior_failures_30d?: number;
  is_first_time_customer?: boolean;
  day_of_month?: number;
  assume_recoverable?: boolean | null;
}

export interface SimulateResult {
  event_id: string;
  final_status: string;
  steps: AuditStep[];
}

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request to ${path} failed with ${res.status}`);
  }
  return res.json();
}

export const api = {
  getBatchSummary: () => fetchJSON<BatchSummary>("/batch/summary"),
  getBatchEvents: () => fetchJSON<{ events: EventSummary[] }>("/batch/events"),
  getEventAudit: (eventId: string) =>
    fetchJSON<{ event_id: string; steps: AuditStep[] }>(`/events/${eventId}/audit`),
  getModelMetrics: () => fetchJSON<ModelMetrics>("/model/metrics"),
  runBatch: (n?: number, live?: boolean) => {
    const params = new URLSearchParams();
    if (n) params.set("n", String(n));
    if (live) params.set("live", "true");
    return fetchJSON<{ status: string; metrics: BatchSummary }>(
      `/batch/run?${params.toString()}`,
      { method: "POST" }
    );
  },
  simulate: (req: SimulateRequest) =>
    fetchJSON<SimulateResult>("/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),
};
