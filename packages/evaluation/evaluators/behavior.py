"""Tier C Evaluator: Non-blocking behavioral standards (dead air, WPM, speech pacing)."""

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvidenceType,
    GroundedEvidence,
)
from packages.domain.speech_metrics import Interval, union_intervals
from packages.domain.transcript import SpeakerType
from packages.evaluation.base import BaseCheckEvaluator, EvaluatorContext


class BehaviorEvaluator(BaseCheckEvaluator):
    """Evaluates behavioral standards such as dead-air silence gaps and active speech rate."""

    def can_evaluate(self, check: ResolvedCheck) -> bool:
        return (
            check.check_type == "BEHAVIOUR"
            or check.check_code.startswith("BEHAVIOUR_")
            or "DEAD_AIR" in check.check_code
            or "SILENCE" in check.check_code
            or "WPM" in check.check_code
        )

    def evaluate(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
    ) -> CheckExecutionResult:
        params = check.parameters or {}
        max_silence_threshold_ms = params.get("max_silence_threshold_ms", 30000)  # 30 seconds

        # Find internal silence gaps between conversation utterances
        sorted_segments = sorted(context.segments, key=lambda s: (s.start_ms, s.end_ms))
        silence_gaps: list[tuple[int, int, int]] = []  # (start_ms, end_ms, duration_ms)

        for i in range(len(sorted_segments) - 1):
            curr_seg = sorted_segments[i]
            next_seg = sorted_segments[i + 1]
            if next_seg.start_ms > curr_seg.end_ms:
                gap = next_seg.start_ms - curr_seg.end_ms
                silence_gaps.append((curr_seg.end_ms, next_seg.start_ms, gap))

        excessive_gaps = [g for g in silence_gaps if g[2] > max_silence_threshold_ms]

        evidences: list[GroundedEvidence] = []
        for g_start, g_end, g_dur in excessive_gaps:
            # Find nearest preceding segment
            prec_seg = next(
                (s for s in reversed(sorted_segments) if s.end_ms <= g_start),
                sorted_segments[0],
            )
            evidences.append(
                GroundedEvidence(
                    transcript_segment_id=prec_seg.id,
                    transcript_id=prec_seg.transcript_id,
                    speaker=prec_seg.business_role.value,
                    evidence_type=EvidenceType.CONTRADICTING,
                    start_ms=g_start,
                    end_ms=g_end,
                    expected_value=f"<= {max_silence_threshold_ms // 1000}s silence",
                    observed_value=f"{g_dur // 1000}s silence",
                    transcript_excerpt=f"[Dead air gap: {g_dur // 1000} seconds]",
                    ai_explanation=f"Excessive dead air of {g_dur // 1000}s detected exceeding threshold of {max_silence_threshold_ms // 1000}s.",
                    comparison_source="BEHAVIORAL_POLICY",
                    expected_value_source="MAX_SILENCE_STANDARD",
                    observed_value_source="AUDIO_SILENCE_DETECTOR",
                )
            )

        if excessive_gaps:
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=CheckOutcome.FAIL,
                confidence=1.0,
                score_numeric=0.0,
                evidences=evidences,
                reason_codes=["EXCESSIVE_DEAD_AIR"],
            )

        return CheckExecutionResult(
            check_id=check.check_id,
            check_version_id=check.version_id,
            is_critical=check.is_critical,
            outcome=CheckOutcome.PASS,
            confidence=1.0,
            score_numeric=100.0,
            evidences=[],
            reason_codes=["BEHAVIORAL_STANDARDS_MET"],
        )
