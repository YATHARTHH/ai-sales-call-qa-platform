"""SQLAlchemy implementation of EvaluationRepositoryPort."""

import json
from dataclasses import asdict
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.application.ports.repositories import EvaluationRepositoryPort
from packages.application.services.snapshot_serializer import serialize_canonical_json
from packages.domain.evaluation import (
    CheckOutcome,
    EvaluationResult,
    EvaluationRun,
    Evidence,
    EvidenceType,
    GateDecision,
    HumanReview,
)
from packages.domain.state import GateStatus
from packages.infrastructure.database.models.evaluations import (
    EvaluationResultModel,
    EvaluationRunModel,
    EvidenceModel,
    GateDecisionModel,
    HumanReviewModel,
)


class SqlAlchemyEvaluationRepository(EvaluationRepositoryPort):
    """Persistence adapter for evaluation runs, results, grounded evidence, and gate decisions."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def save_evaluation_run(
        self,
        run: EvaluationRun,
        results: list[EvaluationResult],
        evidence_items: list[Evidence],
    ) -> None:
        snap_dict = (
            json.loads(serialize_canonical_json(run.input_snapshot))
            if run.input_snapshot
            else None
        )
        snap_id = run.input_snapshot.snapshot_id if run.input_snapshot else run.input_snapshot_id
        snap_hash = run.input_snapshot.snapshot_content_hash if run.input_snapshot else run.input_snapshot_hash

        run_model = EvaluationRunModel(
            id=run.id,
            sale_id=run.sale_id,
            tenant_id=run.tenant_id,
            transcript_id=run.transcript_id,
            checklist_version_id=run.checklist_version_id,
            status=run.status.value if hasattr(run.status, "value") else str(run.status),
            input_snapshot_id=snap_id,
            input_snapshot_hash=snap_hash,
            input_snapshot_json=snap_dict,
            model_provider=run.provenance.provider,
            model_name=run.provenance.model,
            model_version=run.provenance.model_version,
            prompt_template_version=run.provenance.prompt_version,
            pipeline_git_sha=run.provenance.pipeline_git_sha,
            policy_version=run.provenance.policy_version,
            temperature=run.provenance.temperature,
            seed=run.provenance.seed,
            latency_ms=int(run.execution_metadata.latency_ms) if run.execution_metadata else None,
            prompt_tokens=run.execution_metadata.input_tokens if run.execution_metadata else None,
            completion_tokens=run.execution_metadata.output_tokens
            if run.execution_metadata
            else None,
            total_tokens=(
                run.execution_metadata.input_tokens + run.execution_metadata.output_tokens
            )
            if run.execution_metadata
            else None,
            cost_usd=run.execution_metadata.estimated_cost_usd if run.execution_metadata else None,
            created_at=run.created_at,
        )
        await self._session.merge(run_model)

        for res in results:
            res_val = res.result.value if hasattr(res.result, "value") else str(res.result)
            res_model = EvaluationResultModel(
                id=res.id,
                evaluation_run_id=res.evaluation_run_id,
                check_id=res.check_id or res.check_version_id,
                check_version_id=res.check_version_id,
                is_critical=res.is_critical,
                result=res_val,
                confidence=res.confidence,
                score_numeric=res.score_numeric,
                reason_codes=res.reason_codes or [],
                created_at=res.created_at,
            )
            await self._session.merge(res_model)

        for ev in evidence_items:
            ev_type = ev.evidence_type.value if hasattr(ev.evidence_type, "value") else str(ev.evidence_type)
            ev_model = EvidenceModel(
                id=ev.id,
                evaluation_result_id=ev.evaluation_result_id,
                transcript_segment_id=ev.transcript_segment_id,
                transcript_id=ev.transcript_id,
                speaker=ev.speaker,
                evidence_type=ev_type,
                start_ms=ev.start_ms,
                end_ms=ev.end_ms,
                expected_value=ev.expected_value,
                observed_value=ev.observed_value,
                transcript_excerpt=ev.transcript_excerpt,
                ai_explanation=ev.ai_explanation,
                comparison_source=ev.comparison_source,
                expected_value_source=ev.expected_value_source,
                observed_value_source=ev.observed_value_source,
                created_at=ev.created_at,
            )
            await self._session.merge(ev_model)

        await self._session.flush()

    async def save_gate_decision(self, decision: GateDecision) -> None:
        model = GateDecisionModel(
            id=decision.id,
            sale_id=decision.sale_id,
            evaluation_run_id=decision.evaluation_run_id,
            status=decision.status.value if hasattr(decision.status, "value") else str(decision.status),
            policy_version=decision.policy_version,
            decision_reason_code=decision.decision_reason_code,
            auto_submitted=decision.auto_submitted,
            reason_codes=decision.reason_codes or [],
            blocking_check_ids=decision.blocking_check_ids or [],
            warnings=decision.warnings or [],
            decided_at=decision.decided_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def save_human_review(self, review: HumanReview) -> None:
        model = HumanReviewModel(
            id=review.id,
            gate_decision_id=review.gate_decision_id,
            reviewer_id=review.reviewer_id,
            reviewer_role=review.reviewer_role,
            action=review.action.value if hasattr(review.action, "value") else str(review.action),
            reason_notes=review.reason_notes,
            reviewed_at=review.reviewed_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_gate_decision_by_id(self, decision_id: str) -> GateDecision | None:
        stmt = select(GateDecisionModel).where(GateDecisionModel.id == decision_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        if not model:
            return None
        return GateDecision.create(
            decision_id=model.id,
            sale_id=model.sale_id,
            evaluation_run_id=model.evaluation_run_id,
            status=GateStatus(model.status),
            policy_version=model.policy_version,
            decision_reason_code=model.decision_reason_code,
            auto_submitted=model.auto_submitted,
            reason_codes=model.reason_codes or [],
            blocking_check_ids=model.blocking_check_ids or [],
            warnings=model.warnings or [],
        )

    async def get_gate_decision_by_sale_id(self, sale_id: str) -> GateDecision | None:
        stmt = (
            select(GateDecisionModel)
            .where(GateDecisionModel.sale_id == sale_id)
            .order_by(desc(GateDecisionModel.decided_at))
        )
        result = await self._session.execute(stmt)
        model = result.scalars().first()
        if not model:
            return None
        return GateDecision.create(
            decision_id=model.id,
            sale_id=model.sale_id,
            evaluation_run_id=model.evaluation_run_id,
            status=GateStatus(model.status),
            policy_version=model.policy_version,
            decision_reason_code=model.decision_reason_code,
            auto_submitted=model.auto_submitted,
            reason_codes=model.reason_codes or [],
            blocking_check_ids=model.blocking_check_ids or [],
            warnings=model.warnings or [],
        )

    async def update_gate_decision_status(self, decision_id: str, new_status: str) -> None:
        stmt = (
            update(GateDecisionModel)
            .where(GateDecisionModel.id == decision_id)
            .values(status=new_status)
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_evaluation_lineage(
        self, sale_id: str, tenant_id: str | None = None
    ) -> dict[str, Any] | None:
        stmt = (
            select(EvaluationRunModel)
            .where(EvaluationRunModel.sale_id == sale_id)
            .options(
                selectinload(EvaluationRunModel.results).selectinload(
                    EvaluationResultModel.evidence
                ),
                selectinload(EvaluationRunModel.gate_decision).selectinload(
                    GateDecisionModel.human_reviews
                ),
            )
            .order_by(desc(EvaluationRunModel.created_at))
        )
        if tenant_id:
            stmt = stmt.where(EvaluationRunModel.tenant_id == tenant_id)

        result = await self._session.execute(stmt)
        run = result.scalars().first()
        if not run:
            return None

        lineage: dict[str, Any] = {
            "run_id": run.id,
            "sale_id": run.sale_id,
            "tenant_id": run.tenant_id,
            "transcript_id": run.transcript_id,
            "checklist_version_id": run.checklist_version_id,
            "status": run.status,
            "input_snapshot_id": run.input_snapshot_id,
            "input_snapshot_hash": run.input_snapshot_hash,
            "input_snapshot_json": run.input_snapshot_json,
            "provenance": {
                "model_provider": run.model_provider,
                "model_name": run.model_name,
                "model_version": run.model_version,
                "prompt_template_version": run.prompt_template_version,
                "pipeline_git_sha": run.pipeline_git_sha,
                "policy_version": run.policy_version,
                "temperature": run.temperature,
                "seed": run.seed,
            },
            "execution_metadata": {
                "latency_ms": run.latency_ms,
                "prompt_tokens": run.prompt_tokens,
                "completion_tokens": run.completion_tokens,
                "total_tokens": run.total_tokens,
                "cost_usd": run.cost_usd,
            },
            "results": [
                {
                    "result_id": res.id,
                    "check_id": res.check_id,
                    "check_version_id": res.check_version_id,
                    "is_critical": res.is_critical,
                    "result": res.result,
                    "confidence": res.confidence,
                    "score_numeric": res.score_numeric,
                    "reason_codes": res.reason_codes or [],
                    "evidence": [
                        {
                            "evidence_id": ev.id,
                            "transcript_segment_id": ev.transcript_segment_id,
                            "transcript_id": ev.transcript_id,
                            "speaker": ev.speaker,
                            "evidence_type": ev.evidence_type,
                            "start_ms": ev.start_ms,
                            "end_ms": ev.end_ms,
                            "expected_value": ev.expected_value,
                            "observed_value": ev.observed_value,
                            "transcript_excerpt": ev.transcript_excerpt,
                            "ai_explanation": ev.ai_explanation,
                            "comparison_source": ev.comparison_source,
                            "expected_value_source": ev.expected_value_source,
                            "observed_value_source": ev.observed_value_source,
                        }
                        for ev in res.evidence
                    ],
                }
                for res in run.results
            ],
            "gate_decision": None,
            "human_reviews": [],
        }

        if run.gate_decision:
            lineage["gate_decision"] = {
                "decision_id": run.gate_decision.id,
                "status": run.gate_decision.status,
                "policy_version": run.gate_decision.policy_version,
                "decision_reason_code": run.gate_decision.decision_reason_code,
                "auto_submitted": run.gate_decision.auto_submitted,
                "reason_codes": run.gate_decision.reason_codes or [],
                "blocking_check_ids": run.gate_decision.blocking_check_ids or [],
                "warnings": run.gate_decision.warnings or [],
                "decided_at": run.gate_decision.decided_at.isoformat(),
            }
            lineage["human_reviews"] = [
                {
                    "review_id": hr.id,
                    "reviewer_id": hr.reviewer_id,
                    "reviewer_role": hr.reviewer_role,
                    "action": hr.action,
                    "reason_notes": hr.reason_notes,
                    "reviewed_at": hr.reviewed_at.isoformat(),
                }
                for hr in run.gate_decision.human_reviews
            ]

        return lineage

    async def get_evaluation_queue(
        self,
        tenant_id: str,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        stmt = (
            select(GateDecisionModel, EvaluationRunModel)
            .join(EvaluationRunModel, GateDecisionModel.evaluation_run_id == EvaluationRunModel.id)
            .where(EvaluationRunModel.tenant_id == tenant_id)
            .order_by(desc(GateDecisionModel.decided_at))
            .offset(offset)
            .limit(limit)
        )
        if status:
            stmt = stmt.where(GateDecisionModel.status == status)

        res = await self._session.execute(stmt)
        items = []
        for gate_m, run_m in res.all():
            items.append({
                "decision_id": gate_m.id,
                "sale_id": gate_m.sale_id,
                "evaluation_run_id": run_m.id,
                "tenant_id": run_m.tenant_id,
                "status": gate_m.status,
                "decision_reason_code": gate_m.decision_reason_code,
                "auto_submitted": gate_m.auto_submitted,
                "reason_codes": gate_m.reason_codes or [],
                "blocking_check_ids": gate_m.blocking_check_ids or [],
                "decided_at": gate_m.decided_at.isoformat(),
                "created_at": run_m.created_at.isoformat(),
            })
        return items
