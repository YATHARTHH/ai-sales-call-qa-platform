import { Dashboard, Granularity } from "../types/analytics";
import { apiClient } from "./client";

export interface DashboardQuery {
  granularity?: Granularity;
  days?: number;
  repeatOffenceWindowDays?: number;
  repeatOffenceThreshold?: number;
}

/**
 * Fetch dashboard aggregates. Aggregation happens server-side over the whole window, so the
 * figures do not depend on how many rows the queue view happens to have loaded.
 */
export async function fetchDashboard(query: DashboardQuery = {}): Promise<Dashboard> {
  const params = new URLSearchParams();
  params.set("granularity", query.granularity ?? "daily");
  params.set("days", String(query.days ?? 30));
  if (query.repeatOffenceWindowDays != null) {
    params.set("repeat_offence_window_days", String(query.repeatOffenceWindowDays));
  }
  if (query.repeatOffenceThreshold != null) {
    params.set("repeat_offence_threshold", String(query.repeatOffenceThreshold));
  }
  return apiClient<Dashboard>(`/api/v1/analytics/dashboard?${params.toString()}`);
}
