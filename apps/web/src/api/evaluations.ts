import { apiClient } from "./client";
import { EvaluationLineage, HumanReview, QueueItem } from "../types/evaluation";

export async function fetchQueue(status?: string): Promise<QueueItem[]> {
  const query = status && status !== "ALL" ? `?status=${status}` : "";
  return apiClient<QueueItem[]>(`/api/v1/evaluations/queue${query}`);
}

export async function fetchEvaluation(saleOrRunId: string): Promise<EvaluationLineage> {
  return apiClient<EvaluationLineage>(`/api/v1/evaluations/${saleOrRunId}`);
}

export async function submitHumanReview(
  gateDecisionId: string,
  action: "OVERRIDE_TO_PASS" | "CONFIRM_HOLD" | "CANCEL_SALE",
  reasonNotes: string,
  reviewerRole: string = "qa_auditor"
): Promise<HumanReview> {
  return apiClient<HumanReview>(`/api/v1/evaluations/${gateDecisionId}/review`, {
    method: "POST",
    body: JSON.stringify({
      action,
      reason_notes: reasonNotes,
      reviewer_role: reviewerRole,
    }),
  });
}

export async function rerunEvaluation(
  runId: string,
  mode: "EVALUATION_ONLY" | "FULL_REPROCESSING" = "EVALUATION_ONLY",
  reason: string = "Auditor requested rerun"
): Promise<{ message: string; job_id: string; mode: string }> {
  return apiClient<{ message: string; job_id: string; mode: string }>(
    `/api/v1/evaluations/${runId}/rerun`,
    {
      method: "POST",
      body: JSON.stringify({ mode, reason }),
    }
  );
}
