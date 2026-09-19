"""API contract schemas for QA dashboard aggregates."""

from pydantic import BaseModel, ConfigDict, Field


class MetricBlock(BaseModel):
    """The metric set reported for the whole window and for every breakdown group."""

    model_config = ConfigDict(frozen=True)

    total_sales: int
    first_pass_yield: float = Field(description="Share auto-submitted with no human rework")
    hold_rate: float
    review_rate: float
    pass_rate: float
    critical_fail_rate: float
    avg_score_without_fatal_factors: float | None = None
    avg_score_with_fatal_factors: float | None = None


class PeriodMetrics(MetricBlock):
    """Metrics for one time bucket."""

    period: str


class BreakdownEntry(MetricBlock):
    """Metrics for one agent, team lead, campaign, channel or retailer."""

    key: str
    label: str


class FailingCheck(BaseModel):
    """How often one specific critical check is the thing that fails."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    check_code: str
    failures: int
    failure_rate: float


class RepeatOffence(BaseModel):
    """An agent failing the same critical check repeatedly inside a rolling window."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    agent_name: str
    team_lead_id: str | None = None
    check_id: str
    check_code: str
    occurrences: int
    window_days: int
    window_start: str | None = None
    window_end: str | None = None
    policy_action: str


class AuditorAgreement(BaseModel):
    """Whether human auditors upheld the model, and how the calibration sample is tracking."""

    model_config = ConfigDict(frozen=True)

    reviewed_decisions: int
    upheld: int
    overturned: int
    agreement_rate: float
    calibration_sampled: int
    calibration_sampled_reviewed: int
    calibration_disagreements: int


class DashboardResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str
    granularity: str
    date_from: str | None = None
    date_to: str | None = None
    summary: MetricBlock
    timeseries: list[PeriodMetrics] = Field(default_factory=list)
    by_agent: list[BreakdownEntry] = Field(default_factory=list)
    by_team_lead: list[BreakdownEntry] = Field(default_factory=list)
    by_campaign: list[BreakdownEntry] = Field(default_factory=list)
    by_channel: list[BreakdownEntry] = Field(default_factory=list)
    by_retailer: list[BreakdownEntry] = Field(default_factory=list)
    failing_checks: list[FailingCheck] = Field(default_factory=list)
    repeat_offences: list[RepeatOffence] = Field(default_factory=list)
    auditor_agreement: AuditorAgreement
