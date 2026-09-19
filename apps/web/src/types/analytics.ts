export interface MetricBlock {
  total_sales: number;
  /** Share of sales auto-submitted with no human rework. */
  first_pass_yield: number;
  hold_rate: number;
  review_rate: number;
  pass_rate: number;
  critical_fail_rate: number;
  avg_score_without_fatal_factors: number | null;
  avg_score_with_fatal_factors: number | null;
}

export interface PeriodMetrics extends MetricBlock {
  period: string;
}

export interface BreakdownEntry extends MetricBlock {
  key: string;
  label: string;
}

export interface FailingCheck {
  check_id: string;
  check_code: string;
  failures: number;
  failure_rate: number;
}

export interface RepeatOffence {
  agent_id: string;
  agent_name: string;
  team_lead_id: string | null;
  check_id: string;
  check_code: string;
  occurrences: number;
  window_days: number;
  window_start: string | null;
  window_end: string | null;
  policy_action: string;
}

export interface AuditorAgreement {
  reviewed_decisions: number;
  upheld: number;
  overturned: number;
  agreement_rate: number;
  calibration_sampled: number;
  calibration_sampled_reviewed: number;
  calibration_disagreements: number;
}

export type Granularity = "daily" | "weekly" | "monthly";

export interface Dashboard {
  tenant_id: string;
  granularity: Granularity;
  date_from: string | null;
  date_to: string | null;
  summary: MetricBlock;
  timeseries: PeriodMetrics[];
  by_agent: BreakdownEntry[];
  by_team_lead: BreakdownEntry[];
  by_campaign: BreakdownEntry[];
  by_channel: BreakdownEntry[];
  by_retailer: BreakdownEntry[];
  failing_checks: FailingCheck[];
  repeat_offences: RepeatOffence[];
  auditor_agreement: AuditorAgreement;
}
