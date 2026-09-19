"""Tier C Evaluator: non-blocking behavioural standards.

Behaviour checks never hold a sale. They produce coaching signal — dead air, interruptions, talk
ratio, objection handling and speech rate — measured from the same diarised transcript the
compliance tiers use, so every observation still resolves to a timestamp a reviewer can play.
"""

from collections.abc import Sequence

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvidenceType,
    GroundedEvidence,
)
from packages.domain.speech_metrics import SpeechBehaviorAnalyzer, SpeechBehaviorMetrics
from packages.domain.transcript import SpeakerType, TranscriptSegment
from packages.evaluation.base import BaseCheckEvaluator, EvaluatorContext

_CODE_METRIC_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("DEAD_AIR", "SILENCE"), "DEAD_AIR"),
    (("INTERRUPT", "CROSSTALK", "TALK_OVER"), "INTERRUPTIONS"),
    (("TALK_RATIO", "RAPPORT", "DOMINANCE"), "TALK_RATIO"),
    (("OBJECTION",), "OBJECTION_HANDLING"),
    (("SPEECH_RATE", "WPM", "PACE"), "SPEECH_RATE"),
)


def _resolve_metric(check: ResolvedCheck, params: dict) -> str:
    declared = params.get("metric")
    if declared:
        return str(declared).upper()
    code = check.check_code.upper()
    for tokens, metric in _CODE_METRIC_HINTS:
        if any(token in code for token in tokens):
            return metric
    return "DEAD_AIR"


class BehaviorEvaluator(BaseCheckEvaluator):
    """Evaluates behavioural coaching standards from diarised transcript timings."""

    def can_evaluate(self, check: ResolvedCheck) -> bool:
        return check.check_type == "BEHAVIOUR" or check.check_code.startswith("BEHAVIOUR_")

    def evaluate(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
    ) -> CheckExecutionResult:
        params = check.parameters or {}
        metric = _resolve_metric(check, params)

        segments = sorted(context.segments, key=lambda s: (s.start_ms, s.end_ms))
        if not segments:
            return self._result(
                check, CheckOutcome.NOT_EVALUABLE, [], ["NO_TRANSCRIPT_SEGMENTS"], score=None
            )

        metrics = self._metrics(context, segments, params)

        if metric == "DEAD_AIR":
            return self._evaluate_dead_air(check, segments, metrics, params)
        if metric == "INTERRUPTIONS":
            return self._evaluate_interruptions(check, segments, metrics, params)
        if metric == "TALK_RATIO":
            return self._evaluate_talk_ratio(check, segments, metrics, params)
        if metric == "OBJECTION_HANDLING":
            return self._evaluate_objection_handling(check, segments, params)
        if metric == "SPEECH_RATE":
            return self._evaluate_speech_rate(check, segments, metrics, params)

        return self._result(
            check, CheckOutcome.UNSUPPORTED, [], ["UNSUPPORTED_BEHAVIOUR_METRIC"], score=None
        )

    # ------------------------------------------------------------------
    # Metric computation
    # ------------------------------------------------------------------

    def _metrics(
        self,
        context: EvaluatorContext,
        segments: Sequence[TranscriptSegment],
        params: dict,
    ) -> SpeechBehaviorMetrics:
        if isinstance(context.speech_behavior, SpeechBehaviorMetrics):
            return context.speech_behavior
        analyzer = SpeechBehaviorAnalyzer(
            dead_air_threshold_ms=int(params.get("max_silence_threshold_ms", 45_000)),
            interruption_min_duration_ms=int(params.get("overlap_tolerance_ms", 500)),
        )
        return analyzer.analyze(
            utterances=segments,
            audio_duration_ms=max(s.end_ms for s in segments),
        )

    # ------------------------------------------------------------------
    # Individual metrics
    # ------------------------------------------------------------------

    def _evaluate_dead_air(
        self,
        check: ResolvedCheck,
        segments: Sequence[TranscriptSegment],
        metrics: SpeechBehaviorMetrics,
        params: dict,
    ) -> CheckExecutionResult:
        threshold_ms = int(params.get("max_silence_threshold_ms", 45_000))
        gaps = [gap for gap in metrics.dead_air_gaps if gap.duration_ms > threshold_ms]

        if not gaps:
            return self._result(check, CheckOutcome.PASS, [], ["BEHAVIOURAL_STANDARDS_MET"])

        evidences = []
        for gap in gaps:
            anchor = self._segment_before(segments, gap.start_ms)
            evidences.append(
                self._evidence(
                    anchor,
                    gap.start_ms,
                    gap.end_ms,
                    expected=f"<= {threshold_ms // 1000}s silence",
                    observed=f"{gap.duration_ms // 1000}s silence",
                    excerpt=f"[Dead air: {gap.duration_ms // 1000} seconds]",
                    explanation=(
                        f"Silence of {gap.duration_ms // 1000}s exceeds the "
                        f"{threshold_ms // 1000}s coaching threshold."
                    ),
                    source="DEAD_AIR",
                )
            )
        return self._result(check, CheckOutcome.FAIL, evidences, ["EXCESSIVE_DEAD_AIR"])

    def _evaluate_interruptions(
        self,
        check: ResolvedCheck,
        segments: Sequence[TranscriptSegment],
        metrics: SpeechBehaviorMetrics,
        params: dict,
    ) -> CheckExecutionResult:
        max_allowed = int(params.get("max_interruptions", 3))
        tolerance_ms = int(params.get("overlap_tolerance_ms", 300))

        agent_labels = {s.speaker_label for s in segments if s.business_role == SpeakerType.AGENT}
        offences = [
            candidate
            for candidate in metrics.interruption_candidates
            if candidate.speaker_label in agent_labels
            and candidate.overlap_duration_ms >= tolerance_ms
        ]

        if len(offences) <= max_allowed:
            return self._result(
                check,
                CheckOutcome.PASS,
                [],
                ["INTERRUPTIONS_WITHIN_THRESHOLD"],
            )

        evidences = []
        for candidate in offences:
            anchor = self._segment_at(segments, candidate.start_ms)
            evidences.append(
                self._evidence(
                    anchor,
                    candidate.start_ms,
                    candidate.start_ms + candidate.overlap_duration_ms,
                    expected=f"<= {max_allowed} agent interruptions",
                    observed=f"{len(offences)} agent interruptions",
                    excerpt=anchor.text,
                    explanation=(
                        f"Agent talked over the customer for "
                        f"{candidate.overlap_duration_ms}ms."
                    ),
                    source="INTERRUPTIONS",
                )
            )
        return self._result(check, CheckOutcome.FAIL, evidences, ["EXCESSIVE_INTERRUPTIONS"])

    def _evaluate_talk_ratio(
        self,
        check: ResolvedCheck,
        segments: Sequence[TranscriptSegment],
        metrics: SpeechBehaviorMetrics,
        params: dict,
    ) -> CheckExecutionResult:
        minimum = float(params.get("min_agent_ratio", 0.35))
        maximum = float(params.get("max_agent_ratio", 0.85))
        ratio = metrics.agent_talk_percentage / 100.0

        if metrics.total_speech_ms == 0:
            return self._result(
                check, CheckOutcome.NOT_EVALUABLE, [], ["NO_MEASURABLE_SPEECH"], score=None
            )

        within_band = minimum <= ratio <= maximum
        anchor = segments[0]
        evidence = self._evidence(
            anchor,
            segments[0].start_ms,
            max(s.end_ms for s in segments),
            expected=f"agent talk share between {minimum:.0%} and {maximum:.0%}",
            observed=f"{ratio:.0%}",
            excerpt="[Whole-call talk time measurement]",
            explanation=(
                f"Agent spoke for {metrics.agent_talk_ms / 1000:.0f}s of "
                f"{metrics.total_speech_ms / 1000:.0f}s of speech ({ratio:.0%})."
            ),
            source="TALK_RATIO",
            supporting=within_band,
        )
        return self._result(
            check,
            CheckOutcome.PASS if within_band else CheckOutcome.FAIL,
            [evidence],
            ["TALK_RATIO_WITHIN_BAND"] if within_band else ["TALK_RATIO_OUT_OF_BAND"],
        )

    def _evaluate_speech_rate(
        self,
        check: ResolvedCheck,
        segments: Sequence[TranscriptSegment],
        metrics: SpeechBehaviorMetrics,
        params: dict,
    ) -> CheckExecutionResult:
        minimum = float(params.get("min_wpm", 110))
        maximum = float(params.get("max_wpm", 200))
        wpm = metrics.agent_words_per_minute

        if metrics.agent_talk_ms == 0:
            return self._result(
                check, CheckOutcome.NOT_EVALUABLE, [], ["NO_AGENT_SPEECH"], score=None
            )

        within_band = minimum <= wpm <= maximum
        anchor = segments[0]
        evidence = self._evidence(
            anchor,
            segments[0].start_ms,
            max(s.end_ms for s in segments),
            expected=f"{minimum:.0f}-{maximum:.0f} words per minute",
            observed=f"{wpm:.0f} wpm",
            excerpt="[Whole-call speech rate measurement]",
            explanation=f"Agent averaged {wpm:.0f} words per minute across the call.",
            source="SPEECH_RATE",
            supporting=within_band,
        )
        return self._result(
            check,
            CheckOutcome.PASS if within_band else CheckOutcome.FAIL,
            [evidence],
            ["SPEECH_RATE_WITHIN_BAND"] if within_band else ["SPEECH_RATE_OUT_OF_BAND"],
        )

    def _evaluate_objection_handling(
        self,
        check: ResolvedCheck,
        segments: Sequence[TranscriptSegment],
        params: dict,
    ) -> CheckExecutionResult:
        objection_markers = [str(m).lower() for m in params.get("objection_markers", [])]
        acknowledgement_markers = [
            str(m).lower() for m in params.get("acknowledgement_markers", [])
        ]
        window_ms = int(params.get("response_window_ms", 30_000))

        if not objection_markers:
            return self._result(
                check, CheckOutcome.UNSUPPORTED, [], ["NO_OBJECTION_MARKERS_CONFIGURED"], score=None
            )

        objections = [
            segment
            for segment in segments
            if segment.business_role == SpeakerType.CUSTOMER
            and any(marker in segment.text.lower() for marker in objection_markers)
        ]

        if not objections:
            return self._result(check, CheckOutcome.PASS, [], ["NO_OBJECTIONS_RAISED"])

        unhandled = []
        for objection in objections:
            responded = any(
                segment.business_role == SpeakerType.AGENT
                and objection.end_ms <= segment.start_ms <= objection.end_ms + window_ms
                and any(marker in segment.text.lower() for marker in acknowledgement_markers)
                for segment in segments
            )
            if not responded:
                unhandled.append(objection)

        if not unhandled:
            return self._result(check, CheckOutcome.PASS, [], ["ALL_OBJECTIONS_ACKNOWLEDGED"])

        evidences = [
            self._evidence(
                objection,
                objection.start_ms,
                objection.end_ms,
                expected="agent acknowledgement within "
                f"{window_ms // 1000}s of the objection",
                observed="no acknowledgement detected",
                excerpt=objection.text,
                explanation="Customer objection was not acknowledged by the agent.",
                source="OBJECTION_HANDLING",
            )
            for objection in unhandled
        ]
        return self._result(check, CheckOutcome.FAIL, evidences, ["UNHANDLED_OBJECTION"])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _segment_before(
        self, segments: Sequence[TranscriptSegment], timestamp_ms: int
    ) -> TranscriptSegment:
        return next(
            (s for s in reversed(segments) if s.end_ms <= timestamp_ms),
            segments[0],
        )

    def _segment_at(
        self, segments: Sequence[TranscriptSegment], timestamp_ms: int
    ) -> TranscriptSegment:
        return next(
            (s for s in segments if s.start_ms <= timestamp_ms <= s.end_ms),
            segments[0],
        )

    def _evidence(
        self,
        segment: TranscriptSegment,
        start_ms: int,
        end_ms: int,
        expected: str,
        observed: str,
        excerpt: str,
        explanation: str,
        source: str,
        supporting: bool = False,
    ) -> GroundedEvidence:
        return GroundedEvidence(
            transcript_segment_id=segment.id,
            transcript_id=segment.transcript_id,
            speaker=segment.business_role.value,
            evidence_type=EvidenceType.SUPPORTING if supporting else EvidenceType.CONTRADICTING,
            start_ms=start_ms,
            end_ms=end_ms,
            expected_value=expected,
            observed_value=observed,
            transcript_excerpt=excerpt,
            ai_explanation=explanation,
            comparison_source="BEHAVIOURAL_POLICY",
            expected_value_source="CHECK_VERSION_PARAMETERS",
            observed_value_source=source,
        )

    def _result(
        self,
        check: ResolvedCheck,
        outcome: CheckOutcome,
        evidences: list[GroundedEvidence],
        reason_codes: list[str],
        score: float | None = -1.0,
    ) -> CheckExecutionResult:
        if score == -1.0:
            score = 100.0 if outcome == CheckOutcome.PASS else 0.0
        return CheckExecutionResult(
            check_id=check.check_id,
            check_version_id=check.version_id,
            is_critical=check.is_critical,
            outcome=outcome,
            confidence=1.0 if score is not None else None,
            score_numeric=score,
            evidences=evidences,
            reason_codes=reason_codes,
        )
