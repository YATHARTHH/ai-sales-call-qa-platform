"""Orchestration engine coordinating multi-tier evaluation, snapshotting, and gate decisions."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from packages.application.ports.adjudicator import AdjudicatorPort, NullAdjudicator
from packages.application.services.check_resolver import (
    CheckResolutionService,
    SaleContext,
)
from packages.application.services.snapshot_serializer import (
    create_evaluation_input_snapshot,
)
from packages.application.services.transcript_validator import (
    TranscriptIntegrityResult,
    TranscriptIntegrityValidator,
)
from packages.domain.check_library import CheckDefinition, CheckVersion
from packages.domain.evaluation import (
    CheckExecutionResult,
    EvaluationInputSnapshot,
    EvaluationResult,
    EvaluationRun,
    Evidence,
    GateDecision,
)
from packages.domain.provenance import AIExecutionMetadata, AIProvenance
from packages.domain.speech_metrics import SpeechBehaviorAnalyzer
from packages.domain.transcript import Recording, Transcript, TranscriptSegment
from packages.evaluation.base import EvaluatorContext
from packages.evaluation.evaluators.behavior import BehaviorEvaluator
from packages.evaluation.evaluators.factual import FactualMatchEvaluator
from packages.evaluation.evaluators.verbatim import VerbatimRequirementEvaluator
from packages.evaluation.policy.adjudication_policy import (
    AdjudicationPolicy,
    AmbiguityAdjudicationService,
)
from packages.evaluation.policy.gate_engine import DeterministicPolicyEngine
from packages.evaluation.policy.score_calculator import (
    EvaluationScoreCalculator,
    ScoreCalculationResult,
)
from packages.evaluation.registry import EvaluatorRegistry


@dataclass(frozen=True)
class EvaluationExecutionPayload:
    """Complete in-memory output of an evaluation run ready for atomic persistence."""

    run: EvaluationRun
    results: list[EvaluationResult]
    evidences: list[Evidence]
    gate_decision: GateDecision
    snapshot: EvaluationInputSnapshot
    transcript_integrity: TranscriptIntegrityResult
    score_result: ScoreCalculationResult


class EvaluationOrchestrator:
    """Orchestrates end-to-end evaluation pipeline from snapshot to deterministic gate decision."""

    def __init__(
        self,
        registry: EvaluatorRegistry | None = None,
        adjudicator: AdjudicatorPort | None = None,
        adjudication_policy: AdjudicationPolicy | None = None,
    ):
        if registry is None:
            registry = EvaluatorRegistry([
                VerbatimRequirementEvaluator(),
                FactualMatchEvaluator(),
                BehaviorEvaluator(),
            ])
        self.registry = registry
        # With no adjudicator configured the engine stays fully deterministic and every
        # ambiguous finding goes to a human.
        self.adjudication = AmbiguityAdjudicationService(
            adjudicator=adjudicator or NullAdjudicator(),
            policy=adjudication_policy,
        )

    def execute_evaluation(
        self,
        sale_id: str,
        tenant_id: str,
        transcript: Transcript,
        segments: Sequence[TranscriptSegment],
        recording: Recording | None,
        check_definitions: list[CheckDefinition],
        check_versions_by_id: dict[str, list[CheckVersion]],
        sale_data: dict[str, Any],
        lead_data: dict[str, Any],
        provenance: AIProvenance,
        policy_version: str = "policy.v1",
        evaluator_config_hash: str = "config:default.v1",
        applicability_version: str = "v1",
        run_id: str | None = None,
        execution_metadata: AIExecutionMetadata | None = None,
        clean_call_sample_rate: float = DeterministicPolicyEngine.DEFAULT_CLEAN_CALL_SAMPLE_RATE,
    ) -> EvaluationExecutionPayload:
        # 1. Validate transcript quality and lineage
        tx_integrity = TranscriptIntegrityValidator.validate(
            transcript=transcript,
            segments=segments,
            recording=recording,
        )

        # 2. Extract sale context and resolve active date-effective check versions
        call_date = recording.call_date if recording else transcript.created_at
        sale_ctx = SaleContext(
            fuel_type=sale_data.get("details", {}).get("fuel_type") or sale_data.get("fuel_type"),
            customer_type=sale_data.get("customer_type") or lead_data.get("customer_type"),
            state=sale_data.get("state") or lead_data.get("state"),
            campaign_id=sale_data.get("campaign_id") or lead_data.get("campaign_id"),
        )
        resolved_set = CheckResolutionService.resolve_checks_for_sale(
            check_definitions=check_definitions,
            check_versions_by_id=check_versions_by_id,
            call_date=call_date,
            context=sale_ctx,
        )

        # 3. Create immutable canonical input snapshot
        audio_hash = recording.artifact_id if recording else "unknown_audio"
        snapshot = create_evaluation_input_snapshot(
            sale_id=sale_id,
            tenant_id=tenant_id,
            transcript_id=transcript.id,
            transcript_version_id=transcript.output_artifact_id or transcript.id,
            transcript_content_hash=transcript.transcription_config_hash or "tx_hash",
            audio_artifact_hash=audio_hash,
            sale_snapshot=sale_data,
            lead_snapshot=lead_data,
            resolved_check_snapshots=resolved_set.to_snapshot_list(),
            policy_version=policy_version,
            evaluator_config_hash=evaluator_config_hash,
            applicability_version=applicability_version,
        )

        # 4. If transcript integrity is invalid, fail early deterministically
        if not tx_integrity.is_valid:
            score_res = ScoreCalculationResult(
                overall_score=None,
                eligible_check_count=0,
                total_eligible_weight=0,
                is_scoreable=False,
            )
            run = EvaluationRun.create(
                sale_id=sale_id,
                transcript_id=transcript.id,
                checklist_version_id="failed_integrity",
                provenance=provenance,
                tenant_id=tenant_id,
                input_snapshot=snapshot,
                overall_score=None,
                execution_metadata=execution_metadata,
                run_id=run_id,
            )
            gate = DeterministicPolicyEngine.evaluate_gate(
                sale_id=sale_id,
                evaluation_run_id=run.id,
                transcript_integrity=tx_integrity,
                check_results=[],
                resolved_checks=resolved_set.applicable_checks,
                score_result=score_res,
                policy_version=policy_version,
            )
            return EvaluationExecutionPayload(
                run=run,
                results=[],
                evidences=[],
                gate_decision=gate,
                snapshot=snapshot,
                transcript_integrity=tx_integrity,
                score_result=score_res,
            )

        # 5. Execute applicable checks via EvaluatorRegistry.
        # Speech metrics are computed once with permissive detection thresholds so that every
        # gap and overlap is present; each behaviour check then applies its own configured
        # threshold to the same underlying measurements.
        speech_behavior = None
        if segments:
            speech_behavior = SpeechBehaviorAnalyzer(
                dead_air_threshold_ms=1_000,
                interruption_min_duration_ms=1,
            ).analyze(
                utterances=segments,
                audio_duration_ms=(
                    recording.duration_seconds * 1000
                    if recording and recording.duration_seconds
                    else max(s.end_ms for s in segments)
                ),
            )

        eval_context = EvaluatorContext(
            snapshot=snapshot,
            segments=segments,
            sale_data=sale_data,
            lead_data=lead_data,
            speech_behavior=speech_behavior,
        )
        check_execution_results: list[CheckExecutionResult] = []
        for check in resolved_set.applicable_checks:
            res = self.registry.evaluate_check(check, eval_context)
            check_execution_results.append(res)

        # 6. Offer ambiguous findings to the adjudicator. It proposes; the policy below
        # decides, and it may never loosen a critical outcome unless explicitly permitted.
        resolved_by_id = {c.check_id: c for c in resolved_set.applicable_checks}
        check_execution_results = self.adjudication.adjudicate_results(
            results=check_execution_results,
            resolved_checks_by_id=resolved_by_id,
            segments_by_id={segment.id: segment for segment in segments},
            all_segments=list(segments),
        )

        # 7. Calculate QA score
        score_result = EvaluationScoreCalculator.calculate(
            check_results=check_execution_results,
            resolved_checks_by_id=resolved_by_id,
        )

        # 8. Create EvaluationRun domain entity
        run = EvaluationRun.create(
            sale_id=sale_id,
            transcript_id=transcript.id,
            checklist_version_id="chk_set_v1",
            provenance=provenance,
            tenant_id=tenant_id,
            input_snapshot=snapshot,
            overall_score=score_result.overall_score,
            execution_metadata=execution_metadata,
            run_id=run_id,
        )

        # 9. Evaluate policy gate
        gate_decision = DeterministicPolicyEngine.evaluate_gate(
            sale_id=sale_id,
            evaluation_run_id=run.id,
            transcript_integrity=tx_integrity,
            check_results=check_execution_results,
            resolved_checks=resolved_set.applicable_checks,
            score_result=score_result,
            policy_version=policy_version,
            clean_call_sample_rate=clean_call_sample_rate,
        )

        # 10. Convert execution results and evidences to persistent domain entities
        domain_results: list[EvaluationResult] = []
        domain_evidences: list[Evidence] = []

        for cr in check_execution_results:
            er = EvaluationResult.create(
                evaluation_run_id=run.id,
                check_id=cr.check_id,
                check_version_id=cr.check_version_id,
                is_critical=cr.is_critical,
                result=cr.outcome,
                confidence=cr.confidence,
                score_numeric=cr.score_numeric,
                reason_codes=cr.reason_codes,
            )
            domain_results.append(er)

            for ge in cr.evidences:
                ev = Evidence.create(
                    evaluation_result_id=er.id,
                    transcript_segment_id=ge.transcript_segment_id,
                    start_ms=ge.start_ms,
                    end_ms=ge.end_ms,
                    expected_value=ge.expected_value,
                    observed_value=ge.observed_value,
                    transcript_excerpt=ge.transcript_excerpt,
                    ai_explanation=ge.ai_explanation,
                    transcript_id=ge.transcript_id,
                    speaker=ge.speaker,
                    evidence_type=ge.evidence_type,
                    comparison_source=ge.comparison_source,
                    expected_value_source=ge.expected_value_source,
                    observed_value_source=ge.observed_value_source,
                )
                domain_evidences.append(ev)

        return EvaluationExecutionPayload(
            run=run,
            results=domain_results,
            evidences=domain_evidences,
            gate_decision=gate_decision,
            snapshot=snapshot,
            transcript_integrity=tx_integrity,
            score_result=score_result,
        )
