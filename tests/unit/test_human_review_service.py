"""Unit tests for human review state transitions, role permissions, and cancellation semantics."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from packages.application.services.human_review_service import HumanReviewService
from packages.domain.evaluation import GateDecision, HumanReviewAction
from packages.domain.exceptions import EntityNotFoundError, HumanReviewValidationError
from packages.domain.retail import Sale
from packages.domain.state import GateStatus


@pytest.fixture
def mock_uow():
    uow = MagicMock()
    uow.evaluations = MagicMock()
    uow.evaluations.get_gate_decision_by_id = AsyncMock()
    uow.evaluations.save_human_review = AsyncMock()
    uow.evaluations.update_gate_decision_status = AsyncMock()
    uow.sales = MagicMock()
    uow.sales.get_sale = AsyncMock()
    uow.audit = MagicMock()
    uow.audit.record_event = AsyncMock()
    uow.outbox = MagicMock()
    uow.outbox.save_event = AsyncMock()
    return uow


def make_gate_decision(status: GateStatus = GateStatus.HELD) -> GateDecision:
    return GateDecision.create(
        sale_id="sale-100",
        evaluation_run_id="run-100",
        status=status,
        policy_version="policy.v1",
        decision_reason_code="CRITICAL_CHECK_FAILED",
        decision_id="gate-100",
    )


def make_sale(tenant_id: str = "tenant-cimet") -> Sale:
    return Sale.create(
        lead_id="lead-100",
        retailer_id=tenant_id,
        campaign_id="camp-100",
        agent_id="agent-100",
        sale_date=datetime.now(UTC),
        product_details={"fuel_type": "ELECTRICITY"},
        sale_id="sale-100",
    )


@pytest.mark.asyncio
async def test_human_review_override_to_pass(mock_uow):
    gate = make_gate_decision(GateStatus.HELD)
    sale = make_sale("tenant-cimet")
    mock_uow.evaluations.get_gate_decision_by_id.return_value = gate
    mock_uow.sales.get_sale.return_value = sale

    result = await HumanReviewService.process_review(
        uow=mock_uow,
        gate_decision_id="gate-100",
        reviewer_id="user-tl",
        action=HumanReviewAction.OVERRIDE_TO_PASS,
        reason_notes="Verified customer verbally confirmed peak rate earlier in call.",
        reviewer_role="team_lead",
        tenant_id="tenant-cimet",
    )

    assert result["new_gate_status"] == GateStatus.PASSED.value
    assert result["sale_disposition"] == "APPROVED"
    mock_uow.evaluations.update_gate_decision_status.assert_awaited_once_with(
        "gate-100", GateStatus.PASSED.value
    )
    mock_uow.outbox.save_event.assert_awaited_once()
    outbox_call = mock_uow.outbox.save_event.call_args[1]
    assert outbox_call["event_type"] == "GateDecisionOverridden"
    assert outbox_call["aggregate_id"] == "sale-100"


@pytest.mark.asyncio
async def test_human_review_confirm_hold(mock_uow):
    gate = make_gate_decision(GateStatus.REVIEW_REQUIRED)
    sale = make_sale("tenant-cimet")
    mock_uow.evaluations.get_gate_decision_by_id.return_value = gate
    mock_uow.sales.get_sale.return_value = sale

    result = await HumanReviewService.process_review(
        uow=mock_uow,
        gate_decision_id="gate-100",
        reviewer_id="user-qa",
        action=HumanReviewAction.CONFIRM_HOLD,
        reason_notes="Confirmed critical disclosure was omitted by agent.",
        reviewer_role="qa_auditor",
        tenant_id="tenant-cimet",
    )

    assert result["new_gate_status"] == GateStatus.HELD.value
    assert result["sale_disposition"] == "HELD"
    mock_uow.outbox.save_event.assert_awaited_once()
    assert mock_uow.outbox.save_event.call_args[1]["event_type"] == "GateDecisionConfirmed"


@pytest.mark.asyncio
async def test_human_review_cancel_sale_preserves_held_and_requests_cancellation(mock_uow):
    gate = make_gate_decision(GateStatus.HELD)
    sale = make_sale("tenant-cimet")
    mock_uow.evaluations.get_gate_decision_by_id.return_value = gate
    mock_uow.sales.get_sale.return_value = sale

    result = await HumanReviewService.process_review(
        uow=mock_uow,
        gate_decision_id="gate-100",
        reviewer_id="user-qa",
        action=HumanReviewAction.CANCEL_SALE,
        reason_notes="Customer expressed explicit refusal of transfer at end of call.",
        reviewer_role="qa_auditor",
        tenant_id="tenant-cimet",
    )

    # Correction #7: Gate decision remains HELD, sale disposition transitions to CANCEL_REQUESTED
    assert result["new_gate_status"] == GateStatus.HELD.value
    assert result["sale_disposition"] == "CANCEL_REQUESTED"

    mock_uow.evaluations.update_gate_decision_status.assert_awaited_once_with(
        "gate-100", GateStatus.HELD.value
    )
    mock_uow.outbox.save_event.assert_awaited_once()
    outbox_call = mock_uow.outbox.save_event.call_args[1]
    assert outbox_call["event_type"] == "CancellationRequested"
    assert outbox_call["payload"]["sale_disposition"] == "CANCEL_REQUESTED"


@pytest.mark.asyncio
async def test_human_review_rejects_already_passed_gate(mock_uow):
    gate = make_gate_decision(GateStatus.PASSED)
    sale = make_sale("tenant-cimet")
    mock_uow.evaluations.get_gate_decision_by_id.return_value = gate
    mock_uow.sales.get_sale.return_value = sale

    with pytest.raises(HumanReviewValidationError, match="already PASSED"):
        await HumanReviewService.process_review(
            uow=mock_uow,
            gate_decision_id="gate-100",
            reviewer_id="user-tl",
            action=HumanReviewAction.OVERRIDE_TO_PASS,
            reason_notes="Trying to override passed gate",
            tenant_id="tenant-cimet",
        )


@pytest.mark.asyncio
async def test_human_review_rejects_cross_tenant_access(mock_uow):
    gate = make_gate_decision(GateStatus.HELD)
    sale = make_sale("tenant-other")  # Different tenant!
    mock_uow.evaluations.get_gate_decision_by_id.return_value = gate
    mock_uow.sales.get_sale.return_value = sale

    # Rejection returns EntityNotFoundError (404) to avoid leaking existence
    with pytest.raises(EntityNotFoundError):
        await HumanReviewService.process_review(
            uow=mock_uow,
            gate_decision_id="gate-100",
            reviewer_id="user-tl",
            action=HumanReviewAction.OVERRIDE_TO_PASS,
            reason_notes="Attempted cross tenant override",
            tenant_id="tenant-cimet",
        )
