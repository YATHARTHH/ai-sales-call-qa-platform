export type GateStatus = "PASSED" | "HELD" | "REVIEW_REQUIRED" | "CANCELLED";

export interface GroundedEvidence {
  evidence_id: string;
  transcript_segment_id: string;
  transcript_id: string;
  speaker: string;
  evidence_type: string;
  start_ms: number;
  end_ms: number;
  expected_value: any;
  observed_value: any;
  transcript_excerpt: string;
  ai_explanation: string;
  comparison_source?: string | null;
}

export interface CheckResult {
  result_id: string;
  check_id: string;
  check_version_id: string;
  is_critical: boolean;
  result: "PASS" | "FAIL" | "AMBIGUOUS" | "NOT_EVALUABLE" | "UNSUPPORTED" | "ERROR";
  confidence: number | null;
  score_numeric: number | null;
  reason_codes: string[];
  evidence: GroundedEvidence[];
}

export interface GateDecision {
  decision_id: string;
  status: GateStatus;
  policy_version: string;
  decision_reason_code: string;
  auto_submitted: boolean;
  reason_codes: string[];
  blocking_check_ids: string[];
  warnings: string[];
  decided_at: string;
}

export interface HumanReview {
  review_id: string;
  reviewer_id: string;
  reviewer_role: string;
  action: "OVERRIDE_TO_PASS" | "CONFIRM_HOLD" | "CANCEL_SALE";
  reason_notes: string;
  reviewed_at: string;
}

export interface EvaluationLineage {
  run_id: string;
  sale_id: string;
  tenant_id: string;
  transcript_id: string;
  recording_id?: string | null;
  checklist_version_id: string;
  status: string;
  input_snapshot_id?: string | null;
  input_snapshot_hash?: string | null;
  provenance: {
    model_provider: string;
    model_name: string;
    model_version: string;
    pipeline_git_sha: string;
    policy_version: string;
  };
  execution_metadata: {
    latency_ms?: number | null;
    total_tokens?: number | null;
    cost_usd?: number | null;
  };
  results: CheckResult[];
  gate_decision?: GateDecision | null;
  human_reviews: HumanReview[];
}

export interface QueueItem {
  decision_id: string;
  sale_id: string;
  evaluation_run_id: string;
  tenant_id: string;
  status: GateStatus;
  decision_reason_code: string;
  auto_submitted: boolean;
  reason_codes: string[];
  blocking_check_ids: string[];
  decided_at: string;
  created_at: string;
  customer_name?: string | null;
  agent_name?: string | null;
  campaign_name?: string | null;
  overall_score?: number | null;
  recording_id?: string | null;
}
