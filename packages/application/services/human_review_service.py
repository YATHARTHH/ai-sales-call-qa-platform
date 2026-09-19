"""Application service implementing human review overrides and cancellation workflows."""

from datetime import UTC, datetime

from packages.application.ports.repositories import UnitOfWorkPort
from packages.domain.audit import ActorType, AuditEvent
from packages.domain.evaluation import HumanReview, HumanReviewAction
from packages.domain.exceptions import EntityNotFoundError, HumanReviewValidationError
from packages.domain.state import GateStatus


class HumanReviewService:
    """Coordinates Team Lead / QA overrides with audit trails and transactional outbox events."""

    @classmethod
    async def process_review(
        cls,
        uow: UnitOfWorkPort,
        gate_decision_id: str,
        reviewer_id: str,
        action: HumanReviewAction,
        reason_notes: str,
        reviewer_role: str = "qa_auditor",
        tenant_id: str | None = None,
        correlation_id: str = "none",
    ) -> dict[str, str]:
        # 1. Fetch gate decision
        gate = await uow.evaluations.get_gate_decision_by_id(gate_decision_id)
        if not gate:
            raise EntityNotFoundError("GateDecision", gate_decision_id)

        # 2. Fetch sale and verify tenant isolation
        sale = await uow.sales.get_sale(gate.sale_id)
        if not sale:
            raise EntityNotFoundError("Sale", gate.sale_id)

        if tenant_id and sale.retailer_id != tenant_id:
            # Prevent cross-tenant information disclosure
            raise EntityNotFoundError("GateDecision", gate_decision_id)

        # 3. Validate gate decision state machine
        if gate.status == GateStatus.PASSED:
            raise HumanReviewValidationError(
                f"Gate decision '{gate_decision_id}' is already PASSED and cannot be manually reviewed."
            )

        prev_gate_status = gate.status.value

        # 4. Determine state transitions and cancellation semantics
        if action == HumanReviewAction.OVERRIDE_TO_PASS:
            new_gate_status = GateStatus.PASSED
            sale_disposition = "APPROVED"
            audit_action = "GATE_DECISION_OVERRIDDEN"
            outbox_type = "GateDecisionOverridden"
        elif action == HumanReviewAction.CONFIRM_HOLD:
            new_gate_status = GateStatus.HELD
            sale_disposition = "HELD"
            audit_action = "GATE_DECISION_CONFIRMED"
            outbox_type = "GateDecisionConfirmed"
        elif action == HumanReviewAction.CANCEL_SALE:
            # Correction #7: Gate decision remains HELD, sale transitions to CANCEL_REQUESTED
            new_gate_status = GateStatus.HELD
            sale_disposition = "CANCEL_REQUESTED"
            audit_action = "SALE_CANCELLATION_REQUESTED"
            outbox_type = "CancellationRequested"
        else:
            raise HumanReviewValidationError(f"Unsupported review action: '{action}'")

        # 5. Create immutable HumanReview record
        review = HumanReview.create(
            gate_decision_id=gate.id,
            reviewer_id=reviewer_id,
            reviewer_role=reviewer_role,
            action=action,
            reason_notes=reason_notes,
        )
        await uow.evaluations.save_human_review(review)

        # 6. Update gate decision status
        await uow.evaluations.update_gate_decision_status(gate.id, new_gate_status.value)

        # 7. Record immutable AuditEvent
        audit = AuditEvent.record(
            entity_type="GATE_DECISION",
            entity_id=gate.id,
            action=audit_action,
            actor_type=ActorType.HUMAN,
            actor_id=reviewer_id,
            correlation_id=correlation_id,
            payload_json={
                "action": action.value,
                "previous_gate_status": prev_gate_status,
                "new_gate_status": new_gate_status.value,
                "sale_disposition": sale_disposition,
                "reason_notes": reason_notes,
                "reviewer_role": reviewer_role,
            },
        )
        await uow.audit.record_event(audit)

        # 8. Record Outbox Event for reliable asynchronous propagation
        idempotency_key = f"outbox:review:{review.id}:{outbox_type}"
        await uow.outbox.save_event(
            event_type=outbox_type,
            aggregate_type="SALE",
            aggregate_id=sale.id,
            payload={
                "sale_id": sale.id,
                "gate_decision_id": gate.id,
                "review_id": review.id,
                "action": action.value,
                "previous_gate_status": prev_gate_status,
                "new_gate_status": new_gate_status.value,
                "sale_disposition": sale_disposition,
                "reviewer_id": reviewer_id,
                "reason_notes": reason_notes,
            },
            tenant_id=sale.retailer_id,
            idempotency_key=idempotency_key,
        )

        return {
            "review_id": review.id,
            "gate_decision_id": gate.id,
            "action": action.value,
            "previous_gate_status": prev_gate_status,
            "new_gate_status": new_gate_status.value,
            "sale_disposition": sale_disposition,
            "reviewed_at": review.reviewed_at.isoformat(),
        }
