"""Deterministic policy governing how an adjudicator's proposal may change a check outcome.

The adjudicator proposes; this module decides. Two rules do the work:

1. Only AMBIGUOUS findings are eligible. A deterministic PASS, FAIL, NOT_EVALUABLE or UNSUPPORTED
   is never revisited, so a model can neither rescue a failed critical check nor overturn a
   verified one.
2. By default a proposal may only make a critical outcome stricter. Turning an unresolved critical
   check into a pass is the one move that could let a non-compliant sale ship, so it stays with a
   human unless an operator explicitly enables it.
"""

from dataclasses import dataclass, replace

from packages.application.ports.adjudicator import (
    AdjudicationRequest,
    AdjudicationSegment,
    AdjudicationVerdict,
    AdjudicationVerdictType,
    AdjudicatorPort,
)
from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvidenceType,
    GroundedEvidence,
)
from packages.domain.transcript import TranscriptSegment

MAX_CANDIDATE_SEGMENTS = 40


@dataclass(frozen=True)
class AdjudicationPolicy:
    """Rules under which an adjudicator proposal is allowed to change an outcome."""

    # Minimum confidence before a proposal is applied at all.
    min_confidence: float = 0.85
    # Whether an unresolved critical check may be upgraded to PASS by a proposal.
    allow_upgrade_to_pass_on_critical: bool = False
    # Confidence recorded on an outcome the adjudicator resolved.
    resolved_confidence: float = 0.90


class AmbiguityAdjudicationService:
    """Applies adjudicator proposals to ambiguous findings under a deterministic policy."""

    def __init__(
        self,
        adjudicator: AdjudicatorPort,
        policy: AdjudicationPolicy | None = None,
    ):
        self.adjudicator = adjudicator
        self.policy = policy or AdjudicationPolicy()

    def adjudicate_results(
        self,
        results: list[CheckExecutionResult],
        resolved_checks_by_id: dict[str, ResolvedCheck],
        segments_by_id: dict[str, TranscriptSegment],
        all_segments: list[TranscriptSegment],
    ) -> list[CheckExecutionResult]:
        """Return the results with eligible ambiguous findings resolved where policy permits."""
        adjudicated: list[CheckExecutionResult] = []

        for result in results:
            if result.outcome != CheckOutcome.AMBIGUOUS:
                adjudicated.append(result)
                continue

            check = resolved_checks_by_id.get(result.check_id)
            if check is None:
                adjudicated.append(result)
                continue

            request = self._build_request(result, check, all_segments)
            verdict = self.adjudicator.adjudicate(request)
            adjudicated.append(
                self._apply(result, check, verdict, segments_by_id, request)
            )

        return adjudicated

    # ------------------------------------------------------------------

    def _build_request(
        self,
        result: CheckExecutionResult,
        check: ResolvedCheck,
        all_segments: list[TranscriptSegment],
    ) -> AdjudicationRequest:
        # Prefer the lines the evaluator already anchored on; fall back to the start of the call
        # so the adjudicator always has something concrete to reason over.
        cited_ids = {evidence.transcript_segment_id for evidence in result.evidences}
        candidates = [segment for segment in all_segments if segment.id in cited_ids]
        if not candidates:
            candidates = list(all_segments)[:MAX_CANDIDATE_SEGMENTS]

        expected = observed = None
        if result.evidences:
            expected = str(result.evidences[-1].expected_value)
            observed = str(result.evidences[-1].observed_value)

        parameters = check.parameters or {}
        requirement = check.name
        phrases = parameters.get("required_phrases")
        anchors = parameters.get("mandatory_concept_anchors")
        if phrases:
            requirement = f"{check.name}. Approved script: {phrases[0]}"
        elif anchors:
            requirement = f"{check.name}. Must convey: {', '.join(anchors)}"

        return AdjudicationRequest(
            check_code=check.check_code,
            check_name=check.name,
            requirement=requirement,
            expected_value=expected,
            observed_value=observed,
            engine_outcome=result.outcome.value,
            engine_confidence=result.confidence,
            engine_reason_codes=list(result.reason_codes),
            segments=[
                AdjudicationSegment(
                    segment_id=segment.id,
                    speaker=segment.business_role.value,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    text=segment.text,
                )
                for segment in candidates[:MAX_CANDIDATE_SEGMENTS]
            ],
        )

    def _apply(
        self,
        result: CheckExecutionResult,
        check: ResolvedCheck,
        verdict: AdjudicationVerdict,
        segments_by_id: dict[str, TranscriptSegment],
        request: AdjudicationRequest,
    ) -> CheckExecutionResult:
        if verdict.verdict == AdjudicationVerdictType.CANNOT_DETERMINE:
            return self._annotate(result, verdict, segments_by_id, "ADJUDICATION_UNRESOLVED")

        if verdict.confidence < self.policy.min_confidence:
            return self._annotate(
                result, verdict, segments_by_id, "ADJUDICATION_BELOW_CONFIDENCE_THRESHOLD"
            )

        if verdict.verdict == AdjudicationVerdictType.SATISFIED:
            if check.is_critical and not self.policy.allow_upgrade_to_pass_on_critical:
                # The one move that could ship a non-compliant sale stays with a human.
                return self._annotate(
                    result, verdict, segments_by_id, "ADJUDICATION_PASS_WITHHELD_ON_CRITICAL"
                )
            outcome, score, reason = CheckOutcome.PASS, 100.0, "ADJUDICATED_SATISFIED"
        else:
            outcome, score, reason = CheckOutcome.FAIL, 0.0, "ADJUDICATED_NOT_SATISFIED"

        return replace(
            result,
            outcome=outcome,
            score_numeric=score,
            confidence=self.policy.resolved_confidence,
            reason_codes=[*result.reason_codes, reason],
            evidences=[
                *result.evidences,
                self._verdict_evidence(verdict, segments_by_id, request),
            ],
        )

    def _annotate(
        self,
        result: CheckExecutionResult,
        verdict: AdjudicationVerdict,
        segments_by_id: dict[str, TranscriptSegment],
        reason: str,
    ) -> CheckExecutionResult:
        """Keep the finding ambiguous but record that adjudication was attempted."""
        if verdict.provider == "none":
            return result
        return replace(
            result,
            reason_codes=[*result.reason_codes, reason],
        )

    def _verdict_evidence(
        self,
        verdict: AdjudicationVerdict,
        segments_by_id: dict[str, TranscriptSegment],
        request: AdjudicationRequest,
    ) -> GroundedEvidence:
        segment = (
            segments_by_id.get(verdict.supporting_segment_id)
            if verdict.supporting_segment_id
            else None
        )
        fallback = request.segments[0] if request.segments else None

        return GroundedEvidence(
            transcript_segment_id=(
                segment.id if segment else (fallback.segment_id if fallback else "")
            ),
            transcript_id=segment.transcript_id if segment else "",
            speaker=(
                segment.business_role.value
                if segment
                else (fallback.speaker if fallback else "AGENT")
            ),
            evidence_type=(
                EvidenceType.SUPPORTING
                if verdict.verdict == AdjudicationVerdictType.SATISFIED
                else EvidenceType.CONTRADICTING
            ),
            start_ms=segment.start_ms if segment else (fallback.start_ms if fallback else 0),
            end_ms=segment.end_ms if segment else (fallback.end_ms if fallback else 0),
            expected_value=request.requirement,
            observed_value=verdict.verdict.value,
            transcript_excerpt=segment.text if segment else (fallback.text if fallback else ""),
            ai_explanation=(
                f"{verdict.rationale} "
                f"[adjudicated by {verdict.provider}/{verdict.model}, "
                f"prompt {verdict.prompt_version}, confidence {verdict.confidence:.2f}]"
            ),
            comparison_source="AI_ADJUDICATION",
            expected_value_source="CHECK_VERSION_PARAMETERS",
            observed_value_source=f"{verdict.provider}:{verdict.model}",
        )
