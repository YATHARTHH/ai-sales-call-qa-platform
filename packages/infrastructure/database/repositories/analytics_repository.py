"""Server-side aggregation for the QA dashboards.

Every figure is derived from persisted gate decisions and check results for the requested window,
so the numbers do not depend on what happens to be loaded in a UI page. Rows for the window are
fetched once and folded in Python, which keeps the SQL portable across SQLite and PostgreSQL and
keeps every metric defined in one readable place.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from packages.domain.evaluation import CheckOutcome, HumanReviewAction
from packages.domain.state import GateStatus
from packages.infrastructure.database.models.checks import CheckDefinitionModel
from packages.infrastructure.database.models.evaluations import (
    EvaluationRunModel,
    GateDecisionModel,
)
from packages.infrastructure.database.models.sales import (
    SaleModel,
)

# A human review that keeps the model's outcome counts as agreement; an override counts against it.
_AGREEING_ACTIONS = {HumanReviewAction.CONFIRM_HOLD.value, HumanReviewAction.CANCEL_SALE.value}

MAX_WINDOW_ROWS = 20_000


@dataclass
class _Row:
    """One evaluated sale, flattened to exactly what the dashboards need."""

    sale_id: str
    decided_at: datetime
    status: str
    auto_submitted: bool
    decision_reason_code: str
    agent_id: str | None
    agent_name: str | None
    team_lead_id: str | None
    campaign_id: str | None
    campaign_name: str | None
    campaign_channel: str | None
    retailer_id: str | None
    score_without_fatal: float | None
    has_critical_failure: bool
    failed_critical_check_ids: list[str] = field(default_factory=list)
    review_actions: list[str] = field(default_factory=list)

    @property
    def score_with_fatal(self) -> float | None:
        """Score under the fatal-factor rule: any critical failure zeroes the scorecard."""
        if self.score_without_fatal is None:
            return None
        return 0.0 if self.has_critical_failure else self.score_without_fatal


def _bucket_key(moment: datetime, granularity: str) -> str:
    if granularity == "monthly":
        return moment.strftime("%Y-%m")
    if granularity == "weekly":
        monday = moment - timedelta(days=moment.weekday())
        return monday.strftime("%Y-W%V")
    return moment.strftime("%Y-%m-%d")


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


class SqlAlchemyAnalyticsRepository:
    """Aggregates gate decisions and check results into dashboard metrics."""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    async def _load_rows(
        self,
        tenant_id: str,
        date_from: datetime | None,
        date_to: datetime | None,
    ) -> list[_Row]:
        stmt = (
            select(GateDecisionModel, EvaluationRunModel)
            .join(
                EvaluationRunModel,
                GateDecisionModel.evaluation_run_id == EvaluationRunModel.id,
            )
            .options(
                joinedload(EvaluationRunModel.sale).joinedload(SaleModel.agent),
                joinedload(EvaluationRunModel.sale).joinedload(SaleModel.campaign),
                selectinload(EvaluationRunModel.results),
                selectinload(GateDecisionModel.human_reviews),
            )
            .where(EvaluationRunModel.tenant_id == tenant_id)
            .order_by(GateDecisionModel.decided_at.desc())
            .limit(MAX_WINDOW_ROWS)
        )
        if date_from:
            stmt = stmt.where(GateDecisionModel.decided_at >= date_from)
        if date_to:
            stmt = stmt.where(GateDecisionModel.decided_at <= date_to)

        result = await self._session.execute(stmt)

        rows: list[_Row] = []
        for gate, run in result.unique().all():
            failed_critical = [
                r.check_id
                for r in run.results
                if r.is_critical and r.result == CheckOutcome.FAIL.value
            ]
            sale = run.sale
            agent = sale.agent if sale else None
            campaign = sale.campaign if sale else None

            rows.append(
                _Row(
                    sale_id=gate.sale_id,
                    decided_at=gate.decided_at,
                    status=gate.status,
                    auto_submitted=gate.auto_submitted,
                    decision_reason_code=gate.decision_reason_code,
                    agent_id=agent.id if agent else None,
                    agent_name=agent.name if agent else None,
                    team_lead_id=agent.team_lead_id if agent else None,
                    campaign_id=campaign.id if campaign else None,
                    campaign_name=campaign.name if campaign else None,
                    campaign_channel=campaign.channel if campaign else None,
                    retailer_id=sale.retailer_id if sale else None,
                    score_without_fatal=gate.overall_score,
                    has_critical_failure=bool(failed_critical),
                    failed_critical_check_ids=failed_critical,
                    review_actions=[review.action for review in gate.human_reviews],
                )
            )
        return rows

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _summarise(self, rows: list[_Row]) -> dict[str, Any]:
        total = len(rows)
        passed = sum(1 for r in rows if r.status == GateStatus.PASSED.value)
        held = sum(1 for r in rows if r.status == GateStatus.HELD.value)
        review = sum(1 for r in rows if r.status == GateStatus.REVIEW_REQUIRED.value)
        auto_submitted = sum(1 for r in rows if r.auto_submitted)
        critical_failed = sum(1 for r in rows if r.has_critical_failure)

        return {
            "total_sales": total,
            # First-pass yield: went green with no human rework at all.
            "first_pass_yield": _rate(auto_submitted, total),
            "hold_rate": _rate(held, total),
            "review_rate": _rate(review, total),
            "pass_rate": _rate(passed, total),
            "critical_fail_rate": _rate(critical_failed, total),
            "avg_score_without_fatal_factors": _mean(
                [r.score_without_fatal for r in rows if r.score_without_fatal is not None]
            ),
            "avg_score_with_fatal_factors": _mean(
                [r.score_with_fatal for r in rows if r.score_with_fatal is not None]
            ),
        }

    def _breakdown(self, rows: list[_Row], key, label) -> list[dict[str, Any]]:
        grouped: dict[Any, list[_Row]] = defaultdict(list)
        for row in rows:
            grouped[key(row)].append(row)

        breakdown = [
            {"key": str(group_key), "label": label(group_rows[0]), **self._summarise(group_rows)}
            for group_key, group_rows in grouped.items()
            if group_key is not None
        ]
        return sorted(breakdown, key=lambda entry: entry["total_sales"], reverse=True)

    async def get_dashboard(
        self,
        tenant_id: str,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        granularity: str = "daily",
        repeat_offence_window_days: int = 7,
        repeat_offence_threshold: int = 3,
    ) -> dict[str, Any]:
        """Build the full agent/campaign/TL dashboard for a window."""
        rows = await self._load_rows(tenant_id, date_from, date_to)
        check_names = await self._check_names()

        buckets: dict[str, list[_Row]] = defaultdict(list)
        for row in rows:
            buckets[_bucket_key(row.decided_at, granularity)].append(row)

        return {
            "tenant_id": tenant_id,
            "granularity": granularity,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "summary": self._summarise(rows),
            "timeseries": [
                {"period": period, **self._summarise(bucket_rows)}
                for period, bucket_rows in sorted(buckets.items())
            ],
            "by_agent": self._breakdown(
                rows, lambda r: r.agent_id, lambda r: r.agent_name or r.agent_id or "Unknown"
            ),
            "by_team_lead": self._breakdown(
                rows, lambda r: r.team_lead_id, lambda r: r.team_lead_id or "Unassigned"
            ),
            "by_campaign": self._breakdown(
                rows, lambda r: r.campaign_id, lambda r: r.campaign_name or "Unknown"
            ),
            "by_channel": self._breakdown(
                rows, lambda r: r.campaign_channel, lambda r: r.campaign_channel or "Unknown"
            ),
            "by_retailer": self._breakdown(
                rows, lambda r: r.retailer_id, lambda r: r.retailer_id or "Unknown"
            ),
            "failing_checks": self._failing_checks(rows, check_names),
            "repeat_offences": self._repeat_offences(
                rows, check_names, repeat_offence_window_days, repeat_offence_threshold
            ),
            "auditor_agreement": self._auditor_agreement(rows),
        }

    async def _check_names(self) -> dict[str, str]:
        result = await self._session.execute(
            select(CheckDefinitionModel.id, CheckDefinitionModel.check_code)
        )
        return dict(result.all())

    def _failing_checks(
        self, rows: list[_Row], check_names: dict[str, str]
    ) -> list[dict[str, Any]]:
        """Which specific critical check is failing, and how often."""
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            for check_id in row.failed_critical_check_ids:
                counts[check_id] += 1

        total = len(rows)
        return sorted(
            (
                {
                    "check_id": check_id,
                    "check_code": check_names.get(check_id, check_id),
                    "failures": count,
                    "failure_rate": _rate(count, total),
                }
                for check_id, count in counts.items()
            ),
            key=lambda entry: entry["failures"],
            reverse=True,
        )

    def _repeat_offences(
        self,
        rows: list[_Row],
        check_names: dict[str, str],
        window_days: int,
        threshold: int,
    ) -> list[dict[str, Any]]:
        """Agents failing the same critical check repeatedly inside a rolling window.

        Crossing the threshold flags the team lead and triggers a warning under the performance
        policy, so the window is evaluated as a true sliding window rather than per calendar week.
        """
        occurrences: dict[tuple[str, str], list[datetime]] = defaultdict(list)
        agent_names: dict[str, str] = {}
        team_leads: dict[str, str | None] = {}

        for row in rows:
            if not row.agent_id:
                continue
            agent_names[row.agent_id] = row.agent_name or row.agent_id
            team_leads[row.agent_id] = row.team_lead_id
            for check_id in row.failed_critical_check_ids:
                occurrences[(row.agent_id, check_id)].append(row.decided_at)

        window = timedelta(days=window_days)
        offences: list[dict[str, Any]] = []

        for (agent_id, check_id), moments in occurrences.items():
            moments.sort()
            best_count = 0
            best_window: tuple[datetime, datetime] | None = None
            start_index = 0
            for end_index, moment in enumerate(moments):
                while moment - moments[start_index] > window:
                    start_index += 1
                count = end_index - start_index + 1
                if count > best_count:
                    best_count = count
                    best_window = (moments[start_index], moment)

            if best_count >= threshold:
                offences.append(
                    {
                        "agent_id": agent_id,
                        "agent_name": agent_names.get(agent_id, agent_id),
                        "team_lead_id": team_leads.get(agent_id),
                        "check_id": check_id,
                        "check_code": check_names.get(check_id, check_id),
                        "occurrences": best_count,
                        "window_days": window_days,
                        "window_start": best_window[0].isoformat() if best_window else None,
                        "window_end": best_window[1].isoformat() if best_window else None,
                        "policy_action": "TEAM_LEAD_FLAGGED_PERFORMANCE_WARNING",
                    }
                )

        return sorted(offences, key=lambda entry: entry["occurrences"], reverse=True)

    def _auditor_agreement(self, rows: list[_Row]) -> dict[str, Any]:
        """How often human auditors upheld the model's decision.

        This is the calibration signal: a low agreement rate means the gate is mis-tuned, not that
        the auditors are wrong.
        """
        reviewed = [row for row in rows if row.review_actions]
        agreed = sum(
            1 for row in reviewed if all(action in _AGREEING_ACTIONS for action in row.review_actions)
        )
        overturned = sum(
            1
            for row in reviewed
            if any(
                action == HumanReviewAction.OVERRIDE_TO_PASS.value
                for action in row.review_actions
            )
        )
        sampled = [
            row for row in rows if row.decision_reason_code == "SAMPLED_FOR_CALIBRATION"
        ]
        sampled_reviewed = [row for row in sampled if row.review_actions]
        sampled_overturned = sum(
            1
            for row in sampled_reviewed
            if any(
                action != HumanReviewAction.CONFIRM_HOLD.value
                for action in row.review_actions
            )
        )

        return {
            "reviewed_decisions": len(reviewed),
            "upheld": agreed,
            "overturned": overturned,
            "agreement_rate": _rate(agreed, len(reviewed)),
            "calibration_sampled": len(sampled),
            "calibration_sampled_reviewed": len(sampled_reviewed),
            "calibration_disagreements": sampled_overturned,
        }
