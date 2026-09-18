"""SQLAlchemy implementation of EvaluationRepositoryPort."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from packages.application.ports.repositories import EvaluationRepositoryPort
from packages.domain.evaluation import (
    EvaluationResult,
    EvaluationRun,
    Evidence,
    GateDecision,
    HumanReview,
)
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
        run_model = EvaluationRunModel(
            id=run.id,
            sale_id=run.sale_id,
            transcript_id=run.transcript_id,
            checklist_version_id=run.checklist_version_id,
            status=run.status,
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
            res_model = EvaluationResultModel(
                id=res.id,
                evaluation_run_id=res.evaluation_run_id,
                check_version_id=res.check_version_id,
                result=res.result.value,
                confidence=res.confidence,
                score_numeric=res.score_numeric,
                created_at=res.created_at,
            )
            await self._session.merge(res_model)

        for ev in evidence_items:
            ev_model = EvidenceModel(
                id=ev.id,
                evaluation_result_id=ev.evaluation_result_id,
                transcript_segment_id=ev.transcript_segment_id,
                start_ms=ev.start_ms,
                end_ms=ev.end_ms,
                expected_value=ev.expected_value,
                observed_value=ev.observed_value,
                transcript_excerpt=ev.transcript_excerpt,
                ai_explanation=ev.ai_explanation,
                created_at=ev.created_at,
            )
            await self._session.merge(ev_model)

        await self._session.flush()

    async def save_gate_decision(self, decision: GateDecision) -> None:
        model = GateDecisionModel(
            id=decision.id,
            sale_id=decision.sale_id,
            evaluation_run_id=decision.evaluation_run_id,
            status=decision.status.value,
            policy_version=decision.policy_version,
            decision_reason_code=decision.decision_reason_code,
            auto_submitted=decision.auto_submitted,
            decided_at=decision.decided_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def save_human_review(self, review: HumanReview) -> None:
        model = HumanReviewModel(
            id=review.id,
            gate_decision_id=review.gate_decision_id,
            reviewer_id=review.reviewer_id,
            action=review.action.value,
            reason_notes=review.reason_notes,
            reviewed_at=review.reviewed_at,
        )
        await self._session.merge(model)
        await self._session.flush()

    async def get_evaluation_lineage(self, sale_id: str) -> dict[str, Any] | None:
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
            .order_by(EvaluationRunModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        run = result.scalars().first()
        if not run:
            return None

        lineage: dict[str, Any] = {
            "run_id": run.id,
            "sale_id": run.sale_id,
            "transcript_id": run.transcript_id,
            "checklist_version_id": run.checklist_version_id,
            "status": run.status,
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
                    "check_version_id": res.check_version_id,
                    "result": res.result,
                    "confidence": res.confidence,
                    "score_numeric": res.score_numeric,
                    "evidence": [
                        {
                            "evidence_id": ev.id,
                            "transcript_segment_id": ev.transcript_segment_id,
                            "start_ms": ev.start_ms,
                            "end_ms": ev.end_ms,
                            "expected_value": ev.expected_value,
                            "observed_value": ev.observed_value,
                            "transcript_excerpt": ev.transcript_excerpt,
                            "ai_explanation": ev.ai_explanation,
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
                "decided_at": run.gate_decision.decided_at.isoformat(),
            }
            lineage["human_reviews"] = [
                {
                    "review_id": hr.id,
                    "reviewer_id": hr.reviewer_id,
                    "action": hr.action,
                    "reason_notes": hr.reason_notes,
                    "reviewed_at": hr.reviewed_at.isoformat(),
                }
                for hr in run.gate_decision.human_reviews
            ]

        return lineage
