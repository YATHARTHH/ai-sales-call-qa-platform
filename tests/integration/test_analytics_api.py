"""Integration tests for server-side QA dashboard aggregation."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from apps.api.dependencies import get_current_principal
from apps.api.main import app
from packages.contracts.security import Principal
from packages.domain.check_library import CheckDefinition, CheckType
from packages.domain.evaluation import (
    CheckOutcome,
    EvaluationResult,
    EvaluationRun,
    EvaluationRunStatus,
    GateDecision,
    HumanReview,
    HumanReviewAction,
)
from packages.domain.provenance import AIProvenance
from packages.domain.retail import Agent, Campaign, Lead, Retailer, Sale
from packages.domain.state import GateStatus
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)
from packages.infrastructure.database.repositories import (
    SqlAlchemyCheckLibraryRepository,
    SqlAlchemyEvaluationRepository,
    SqlAlchemySaleRepository,
    SqlAlchemyTranscriptRepository,
)
from packages.infrastructure.database.session import get_db_session

TENANT = "ret-analytics"
NOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)

PROVENANCE = AIProvenance(
    provider="deterministic",
    model="qa-gate-engine",
    model_version="1.0",
    prompt_version="1.0",
    check_version="chk-v1",
    pipeline_git_sha="sha",
    policy_version="policy.v1",
)


async def _seed_sale(
    repos,
    index: int,
    *,
    agent_id: str,
    decided_at: datetime,
    status: GateStatus,
    auto_submitted: bool,
    score: float | None,
    failed_check_id: str | None,
    reason_code: str = "ALL_CRITICAL_CHECKS_PASSED",
    review_action: HumanReviewAction | None = None,
) -> None:
    sale_repo, tr_repo, eval_repo = repos
    sale_id = f"sale-an-{index}"

    await sale_repo.save_lead(
        Lead(
            id=f"lead-an-{index}",
            customer_name=f"Customer {index}",
            customer_email=f"c{index}@test.com",
            phone="0400000000",
        )
    )
    await sale_repo.save_sale(
        Sale.create(
            f"lead-an-{index}", TENANT, "camp-an", agent_id, decided_at, {}, sale_id=sale_id
        )
    )
    await tr_repo.save_recording(
        Recording.create(
            sale_id=sale_id,
            artifact_id=f"art-an-{index}",
            dialler_call_id=f"CALL_AN_{index}",
            duration_seconds=120.0,
            call_date=decided_at,
            recording_id=f"rec-an-{index}",
        )
    )
    transcript = Transcript(
        id=f"tx-an-{index}",
        recording_id=f"rec-an-{index}",
        source_artifact_id=f"art-an-{index}",
        output_artifact_id=f"art-tx-an-{index}",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=120000,
        asr_provider="WHISPER",
        asr_model="whisper-large-v3",
        asr_model_version="2026.1",
        diarization_provider="stereo-channel",
        diarization_version="v1",
        created_at=decided_at,
    )
    await tr_repo.save_transcript(
        transcript,
        [
            TranscriptSegment.create(
                transcript_id=transcript.id,
                segment_order=1,
                business_role=SpeakerType.AGENT,
                start_ms=0,
                end_ms=5000,
                text="Hello.",
                segment_id=f"seg-an-{index}",
            )
        ],
    )

    results = []
    if failed_check_id:
        results.append(
            EvaluationResult(
                id=f"res-an-{index}",
                evaluation_run_id=f"run-an-{index}",
                check_id=failed_check_id,
                check_version_id="chk-v1",
                result=CheckOutcome.FAIL,
                confidence=1.0,
                score_numeric=0.0,
                is_critical=True,
            )
        )
    else:
        results.append(
            EvaluationResult(
                id=f"res-an-{index}",
                evaluation_run_id=f"run-an-{index}",
                check_id="chk-rate",
                check_version_id="chk-v1",
                result=CheckOutcome.PASS,
                confidence=1.0,
                score_numeric=100.0,
                is_critical=True,
            )
        )

    await eval_repo.save_evaluation_run(
        EvaluationRun(
            id=f"run-an-{index}",
            sale_id=sale_id,
            transcript_id=transcript.id,
            checklist_version_id="chk-v1",
            status=EvaluationRunStatus.SUCCEEDED,
            provenance=PROVENANCE,
            created_at=decided_at,
            tenant_id=TENANT,
        ),
        results,
        [],
    )

    decision = GateDecision(
        id=f"gate-an-{index}",
        sale_id=sale_id,
        evaluation_run_id=f"run-an-{index}",
        status=status,
        overall_score=score,
        policy_version="policy.v1",
        decision_reason_code=reason_code,
        auto_submitted=auto_submitted,
        blocking_check_ids=[failed_check_id] if failed_check_id else [],
        decided_at=decided_at,
    )
    await eval_repo.save_gate_decision(decision)

    if review_action:
        await eval_repo.save_human_review(
            HumanReview.create(
                gate_decision_id=decision.id,
                reviewer_id="tl-1",
                action=review_action,
                reason_notes="Reviewed during calibration.",
            )
        )


@pytest.fixture
async def seeded_analytics(test_db_session):
    sale_repo = SqlAlchemySaleRepository(test_db_session)
    tr_repo = SqlAlchemyTranscriptRepository(test_db_session)
    eval_repo = SqlAlchemyEvaluationRepository(test_db_session)
    check_repo = SqlAlchemyCheckLibraryRepository(test_db_session)
    repos = (sale_repo, tr_repo, eval_repo)

    await sale_repo.save_retailer(Retailer(id=TENANT, code="AN", name="Analytics Retailer"))
    await sale_repo.save_campaign(
        Campaign(id="camp-an", code="CAMP_AN", name="Owned Site Energy", channel="OWNED_SITE")
    )
    await sale_repo.save_agent(
        Agent(id="agt-strong", staff_id="S1", name="Strong Agent", email="s@test.com",
              team_lead_id="tl-1")
    )
    await sale_repo.save_agent(
        Agent(id="agt-weak", staff_id="S2", name="Weak Agent", email="w@test.com",
              team_lead_id="tl-1")
    )
    await check_repo.save_check_definition(
        CheckDefinition(
            id="chk-rate",
            check_code="FACTUAL_PEAK_RATE",
            name="Peak Rate",
            check_type=CheckType.FACTUAL_MATCH,
            is_critical=True,
        )
    )

    # Two clean auto-submitted sales from the strong agent.
    for index in (1, 2):
        await _seed_sale(
            repos, index, agent_id="agt-strong", decided_at=NOW - timedelta(days=index),
            status=GateStatus.PASSED, auto_submitted=True, score=100.0, failed_check_id=None,
        )

    # Three rate failures from the weak agent inside a rolling seven days.
    for offset, index in enumerate((3, 4, 5), start=1):
        await _seed_sale(
            repos, index, agent_id="agt-weak", decided_at=NOW - timedelta(days=offset),
            status=GateStatus.HELD, auto_submitted=False, score=40.0,
            failed_check_id="chk-rate", reason_code="CRITICAL_CHECK_FAILED",
            review_action=HumanReviewAction.CONFIRM_HOLD if index == 3 else None,
        )

    # One clean call diverted to a human for calibration.
    await _seed_sale(
        repos, 6, agent_id="agt-strong", decided_at=NOW - timedelta(days=1),
        status=GateStatus.REVIEW_REQUIRED, auto_submitted=False, score=100.0,
        failed_check_id=None, reason_code="SAMPLED_FOR_CALIBRATION",
        review_action=HumanReviewAction.CONFIRM_HOLD,
    )

    await test_db_session.commit()


@pytest.fixture
async def client(test_db_session):
    app.dependency_overrides[get_db_session] = lambda: test_db_session
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id="tl-1", tenant_id=TENANT, roles=["team_lead"]
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_summary_reports_first_pass_yield_over_the_whole_window(
    client, seeded_analytics
):
    response = await client.get("/api/v1/analytics/dashboard?days=30")

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["total_sales"] == 6
    # Two of six sales auto-submitted with no human involvement.
    assert summary["first_pass_yield"] == pytest.approx(2 / 6, abs=1e-4)
    assert summary["hold_rate"] == pytest.approx(3 / 6, abs=1e-4)
    assert summary["critical_fail_rate"] == pytest.approx(3 / 6, abs=1e-4)


@pytest.mark.asyncio
async def test_scores_are_reported_with_and_without_fatal_factors(client, seeded_analytics):
    response = await client.get("/api/v1/analytics/dashboard?days=30")
    summary = response.json()["summary"]

    # Three clean calls at 100 and three failing calls that still carry their weighted 40.
    assert summary["avg_score_without_fatal_factors"] == pytest.approx(70.0, abs=0.01)
    # Under the fatal-factor rule a critical failure zeroes the scorecard: (100*3 + 0*3) / 6.
    assert summary["avg_score_with_fatal_factors"] == pytest.approx(50.0, abs=0.01)


@pytest.mark.asyncio
async def test_breakdown_by_agent_separates_performance(client, seeded_analytics):
    response = await client.get("/api/v1/analytics/dashboard?days=30")
    by_agent = {entry["label"]: entry for entry in response.json()["by_agent"]}

    assert by_agent["Weak Agent"]["critical_fail_rate"] == 1.0
    assert by_agent["Strong Agent"]["critical_fail_rate"] == 0.0


@pytest.mark.asyncio
async def test_rollups_by_team_lead_campaign_and_channel_are_present(client, seeded_analytics):
    body = (await client.get("/api/v1/analytics/dashboard?days=30")).json()

    assert [e["key"] for e in body["by_team_lead"]] == ["tl-1"]
    assert body["by_campaign"][0]["label"] == "Owned Site Energy"
    assert body["by_channel"][0]["label"] == "OWNED_SITE"
    assert body["by_retailer"][0]["key"] == TENANT


@pytest.mark.asyncio
async def test_failing_checks_identify_the_specific_check(client, seeded_analytics):
    body = (await client.get("/api/v1/analytics/dashboard?days=30")).json()

    assert body["failing_checks"][0]["check_code"] == "FACTUAL_PEAK_RATE"
    assert body["failing_checks"][0]["failures"] == 3


@pytest.mark.asyncio
async def test_repeat_offence_flags_three_failures_in_a_rolling_seven_days(
    client, seeded_analytics
):
    body = (await client.get("/api/v1/analytics/dashboard?days=30")).json()

    offences = body["repeat_offences"]
    assert len(offences) == 1
    assert offences[0]["agent_name"] == "Weak Agent"
    assert offences[0]["check_code"] == "FACTUAL_PEAK_RATE"
    assert offences[0]["occurrences"] == 3
    assert offences[0]["team_lead_id"] == "tl-1"
    assert offences[0]["policy_action"] == "TEAM_LEAD_FLAGGED_PERFORMANCE_WARNING"


@pytest.mark.asyncio
async def test_repeat_offence_threshold_is_configurable(client, seeded_analytics):
    body = (await client.get("/api/v1/analytics/dashboard?days=30&repeat_offence_threshold=4")).json()

    assert body["repeat_offences"] == []


@pytest.mark.asyncio
async def test_auditor_agreement_and_calibration_sampling_are_tracked(client, seeded_analytics):
    body = (await client.get("/api/v1/analytics/dashboard?days=30")).json()
    agreement = body["auditor_agreement"]

    assert agreement["reviewed_decisions"] == 2
    assert agreement["upheld"] == 2
    assert agreement["agreement_rate"] == 1.0
    assert agreement["calibration_sampled"] == 1
    assert agreement["calibration_sampled_reviewed"] == 1


@pytest.mark.asyncio
async def test_timeseries_buckets_by_requested_granularity(client, seeded_analytics):
    daily = (await client.get("/api/v1/analytics/dashboard?days=30&granularity=daily")).json()
    monthly = (await client.get("/api/v1/analytics/dashboard?days=30&granularity=monthly")).json()

    assert len(daily["timeseries"]) > len(monthly["timeseries"])
    assert monthly["timeseries"][0]["period"] == "2026-09"
    assert sum(bucket["total_sales"] for bucket in daily["timeseries"]) == 6


@pytest.mark.asyncio
async def test_window_excludes_decisions_outside_the_date_range(client, seeded_analytics):
    body = (await client.get("/api/v1/analytics/dashboard?days=1")).json()

    # Only decisions inside the last day are counted.
    assert body["summary"]["total_sales"] < 6


@pytest.mark.asyncio
async def test_other_tenants_data_is_not_visible(client, seeded_analytics):
    app.dependency_overrides[get_current_principal] = lambda: Principal(
        user_id="other", tenant_id="ret-someone-else", roles=["team_lead"]
    )

    body = (await client.get("/api/v1/analytics/dashboard?days=30")).json()

    assert body["summary"]["total_sales"] == 0
    assert body["repeat_offences"] == []


@pytest.mark.asyncio
async def test_invalid_date_window_is_rejected(client, seeded_analytics):
    response = await client.get(
        "/api/v1/analytics/dashboard"
        "?date_from=2026-09-19T00:00:00%2B00:00&date_to=2026-09-01T00:00:00%2B00:00"
    )

    assert response.status_code == 422
