"""Tier A Evaluator: Verbatim Requirement and Mandatory Disclosure verification."""

import re
from difflib import SequenceMatcher

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvidenceType,
    GroundedEvidence,
)
from packages.domain.transcript import SpeakerType, TranscriptSegment
from packages.evaluation.base import BaseCheckEvaluator, EvaluatorContext


def _normalize(text: str) -> str:
    """Normalizes text for linguistic comparison."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_concept(normalized_text: str, concept: str) -> bool:
    """Checks if concept keywords exist in normalized text."""
    norm_concept = _normalize(concept)
    words = norm_concept.split()
    return all(w in normalized_text for w in words)


class VerbatimRequirementEvaluator(BaseCheckEvaluator):
    """Evaluates verbatim disclosures, regulatory statements, and script requirements."""

    def can_evaluate(self, check: ResolvedCheck) -> bool:
        return check.check_type == "VERBATIM" or check.check_code.startswith("VERBATIM_")

    def evaluate(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
    ) -> CheckExecutionResult:
        params = check.parameters or {}
        concept_anchors: list[str] = params.get("mandatory_concept_anchors", [])
        required_phrases: list[str] = params.get("required_phrases", [])
        pass_threshold = float(params.get("similarity_threshold", 0.80))
        ambiguous_threshold = float(params.get("ambiguous_threshold", pass_threshold - 0.10))
        review_floor = float(params.get("review_floor", 0.55))
        target_role_str = params.get("speaker", "AGENT").upper()
        target_role = (
            SpeakerType.CUSTOMER if target_role_str == "CUSTOMER" else SpeakerType.AGENT
        )

        relevant_segments = [
            s for s in context.segments if s.business_role == target_role
        ]

        best_score = 0.0
        best_segment: TranscriptSegment | None = None
        best_missing_anchors: list[str] = []

        # Compare against individual segments
        for seg in relevant_segments:
            norm_seg = _normalize(seg.text)
            missing = [c for c in concept_anchors if not _contains_concept(norm_seg, c)]

            # Calculate similarity against required phrases
            phrase_sim = 0.0
            if required_phrases:
                for req in required_phrases:
                    norm_req = _normalize(req)
                    sim = SequenceMatcher(None, norm_req, norm_seg).ratio()
                    if sim > phrase_sim:
                        phrase_sim = sim
            else:
                phrase_sim = 1.0 if len(missing) == 0 else 0.0

            # Weight score by concept presence
            if concept_anchors:
                concept_ratio = (len(concept_anchors) - len(missing)) / len(concept_anchors)
                combined_score = 0.6 * concept_ratio + 0.4 * phrase_sim
            else:
                combined_score = phrase_sim

            if combined_score > best_score:
                best_score = combined_score
                best_segment = seg
                best_missing_anchors = missing

        # Also check concatenated adjacent segments if disclosure spans pauses
        if best_score < pass_threshold and len(relevant_segments) > 1:
            for i in range(len(relevant_segments) - 1):
                s1 = relevant_segments[i]
                s2 = relevant_segments[i + 1]
                combined_text = s1.text + " " + s2.text
                norm_comb = _normalize(combined_text)
                missing = [c for c in concept_anchors if not _contains_concept(norm_comb, c)]

                phrase_sim = 0.0
                if required_phrases:
                    for req in required_phrases:
                        sim = SequenceMatcher(None, _normalize(req), norm_comb).ratio()
                        if sim > phrase_sim:
                            phrase_sim = sim
                else:
                    phrase_sim = 1.0 if len(missing) == 0 else 0.0

                if concept_anchors:
                    concept_ratio = (len(concept_anchors) - len(missing)) / len(concept_anchors)
                    comb_score = 0.6 * concept_ratio + 0.4 * phrase_sim
                else:
                    comb_score = phrase_sim

                if comb_score > best_score:
                    best_score = comb_score
                    best_segment = s1
                    best_missing_anchors = missing

        # Deterministic outcome decision
        if (
            len(best_missing_anchors) == 0
            and best_score >= pass_threshold
            and best_segment is not None
        ):
            evidences = [
                GroundedEvidence(
                    transcript_segment_id=best_segment.id,
                    transcript_id=best_segment.transcript_id,
                    speaker=best_segment.business_role.value,
                    evidence_type=EvidenceType.SUPPORTING,
                    start_ms=best_segment.start_ms,
                    end_ms=best_segment.end_ms,
                    expected_value=required_phrases or concept_anchors,
                    observed_value=best_segment.text,
                    transcript_excerpt=best_segment.text,
                    ai_explanation="Mandatory concept anchors and disclosure verified in spoken transcript.",
                    comparison_source="SCRIPT_REQUIREMENT",
                    expected_value_source="CHECK_PARAMETERS",
                    observed_value_source="TRANSCRIPT_AGENT_SPEECH",
                )
            ]
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=CheckOutcome.PASS,
                confidence=0.95,
                score_numeric=100.0,
                evidences=evidences,
                reason_codes=["VERBATIM_DISCLOSURE_VERIFIED"],
            )

        if best_segment is not None and best_score >= review_floor:
            evidences = [
                GroundedEvidence(
                    transcript_segment_id=best_segment.id,
                    transcript_id=best_segment.transcript_id,
                    speaker=best_segment.business_role.value,
                    evidence_type=EvidenceType.CONTRADICTING,
                    start_ms=best_segment.start_ms,
                    end_ms=best_segment.end_ms,
                    expected_value=required_phrases or concept_anchors,
                    observed_value=best_segment.text,
                    transcript_excerpt=best_segment.text,
                    ai_explanation=(
                        f"Partial verbatim match ({int(best_score * 100)}%). "
                        f"Missing anchors: {best_missing_anchors}."
                    ),
                    comparison_source="SCRIPT_REQUIREMENT",
                    expected_value_source="CHECK_PARAMETERS",
                    observed_value_source="TRANSCRIPT_AGENT_SPEECH",
                )
            ]
            # A partial read close to the script is routed to a human rather than failed
            # outright: on noisy audio this band is usually a mishear, not a missing disclosure.
            outcome = (
                CheckOutcome.AMBIGUOUS
                if best_score >= ambiguous_threshold
                else CheckOutcome.FAIL
            )
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=outcome,
                confidence=round(best_score, 2),
                score_numeric=round(best_score * 100.0, 1),
                evidences=evidences,
                reason_codes=["VERBATIM_PARTIAL_OR_AMBIGUOUS_MATCH"],
            )

        return CheckExecutionResult(
            check_id=check.check_id,
            check_version_id=check.version_id,
            is_critical=check.is_critical,
            outcome=CheckOutcome.FAIL,
            confidence=0.95,
            score_numeric=0.0,
            evidences=[],
            reason_codes=["MANDATORY_CONCEPT_MISSING"],
        )
