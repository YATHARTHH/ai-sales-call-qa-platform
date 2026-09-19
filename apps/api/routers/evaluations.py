"""FastAPI router for QA evaluations, lineage queries, human reviews, and rerun orchestration."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.dependencies import get_current_principal, get_queue
from packages.application.ports.queue import QueuePort
from packages.application.services.human_review_service import HumanReviewService
from packages.contracts.evaluations import (
    EvaluationLineageResponse,
    EvaluationQueueItemResponse,
    HumanReviewRequest,
    HumanReviewResponse,
    RerunEvaluationRequest,
)
from packages.contracts.security import Principal
from packages.domain.audit import ActorType, AuditEvent
from packages.domain.exceptions import EntityNotFoundError, HumanReviewValidationError
from packages.domain.jobs import PipelineJob
from packages.infrastructure.database.repositories.unit_of_work import SqlAlchemyUnitOfWork
from packages.infrastructure.database.session import get_db_session
from packages.observability.logging import get_logger

logger = get_logger("api.evaluations")

router = APIRouter(prefix="/api/v1/evaluations", tags=["evaluations"])


@router.get(
    "/queue",
    response_model=list[EvaluationQueueItemResponse],
    summary="Get paginated QA evaluation queue for human audit",
)
async def get_evaluation_queue(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> list[EvaluationQueueItemResponse]:
    """Retrieve tenant-isolated queue of gate decisions awaiting audit or review."""
    uow = SqlAlchemyUnitOfWork(session)
    items = await uow.evaluations.get_evaluation_queue(
        tenant_id=principal.tenant_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [EvaluationQueueItemResponse(**item) for item in items]


@router.get(
    "/{sale_id}",
    response_model=EvaluationLineageResponse,
    summary="Get full unbroken evaluation lineage, evidence, and gate decision",
)
async def get_evaluation_lineage(
    sale_id: str,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> EvaluationLineageResponse:
    """Retrieve comprehensive evaluation lineage. Rejects cross-tenant access with 404."""
    uow = SqlAlchemyUnitOfWork(session)
    lineage = await uow.evaluations.get_evaluation_lineage(
        sale_id=sale_id,
        tenant_id=principal.tenant_id,
    )
    if not lineage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation lineage for sale '{sale_id}' not found.",
        )
    return EvaluationLineageResponse(**lineage)


@router.post(
    "/{gate_decision_id}/review",
    response_model=HumanReviewResponse,
    summary="Submit Team Lead or QA human review override / confirmation / cancellation",
)
async def submit_human_review(
    gate_decision_id: str,
    body: HumanReviewRequest,
    session: AsyncSession = Depends(get_db_session),
    principal: Principal = Depends(get_current_principal),
) -> HumanReviewResponse:
    """Processes human review override with strict state transitions and transactional outbox emission."""
    uow = SqlAlchemyUnitOfWork(session)
    try:
        result = await HumanReviewService.process_review(
            uow=uow,
            gate_decision_id=gate_decision_id,
            reviewer_id=principal.user_id,
            action=body.action,
            reason_notes=body.reason_notes,
            reviewer_role=body.reviewer_role,
            tenant_id=principal.tenant_id,
        )
        await uow.commit()
        return HumanReviewResponse(**result)
    except EntityNotFoundError as exc:
        await uow.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    except HumanReviewValidationError as exc:
        await uow.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except Exception as exc:
        await uow.rollback()
        logger.error("human_review_processing_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record human review.",
        )


@router.post(
    "/{sale_id}/rerun",
    summary="Trigger evaluation rerun or full pipeline reprocessing",
)
async def rerun_evaluation(
    sale_id: str,
    body: RerunEvaluationRequest,
    session: AsyncSession = Depends(get_db_session),
    queue: QueuePort = Depends(get_queue),
    principal: Principal = Depends(get_current_principal),
) -> dict[str, str]:
    """Schedules a rerun job for a sale's latest recording."""
    uow = SqlAlchemyUnitOfWork(session)
    sale = await uow.sales.get_sale(sale_id)
    if not sale or sale.retailer_id != principal.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sale '{sale_id}' not found.",
        )

    # Fetch latest evaluation lineage
    lineage = await uow.evaluations.get_evaluation_lineage(sale_id, principal.tenant_id)
    if not lineage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No prior evaluation exists to rerun for sale '{sale_id}'.",
        )

    # Queue evaluation job
    eval_job = PipelineJob.create(
        recording_id=lineage["transcript_id"],  # Or recording ID
        stage="EVALUATING",
        input_artifact_hash="rerun_requested",
        processor_version="eval_rerun.v1",
    )
    await uow.jobs.save_job_idempotent(eval_job)

    # Record Audit Event
    audit = AuditEvent.record(
        entity_type="EVALUATION_RUN",
        entity_id=lineage["run_id"],
        action="RERUN_REQUESTED",
        actor_type=ActorType.HUMAN,
        actor_id=principal.user_id,
        correlation_id=eval_job.id,
        payload_json={"mode": body.mode.value, "reason": body.reason},
    )
    await uow.audit.record_event(audit)
    await uow.commit()

    # Enqueue to Redis
    await queue.enqueue(
        "queue:evaluation",
        {"job_id": eval_job.id, "recording_id": eval_job.recording_id, "correlation_id": eval_job.id},
    )

    return {
        "status": "QUEUED",
        "sale_id": sale_id,
        "job_id": eval_job.id,
        "mode": body.mode.value,
    }
