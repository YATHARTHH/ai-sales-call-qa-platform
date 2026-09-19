"""Tier B Evaluator: parameter-driven factual comparison of spoken values against CRM records.

The evaluator carries no business expectations of its own. Each check version supplies the
comparator type and the dotted CRM field path(s); the expected value is resolved exclusively from
the immutable sale/lead snapshot. If it cannot be resolved the check returns NOT_EVALUABLE and the
deterministic gate holds the sale — a spoken value is never compared against a fabricated default.

Decision rule (auditable and order-independent):
  1. Only segments matching the check's keyword scope are considered, so unrelated figures spoken
     elsewhere in the call cannot satisfy or break the check.
  2. An explicit verbal correction supersedes every earlier statement of the same value.
  3. If any in-scope candidate matches the CRM value the check passes, citing that utterance;
     other stated values are attached as CONTEXT evidence.
  4. Otherwise the check fails, citing the closest candidate so the reviewer sees the real gap.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvidenceType,
    GroundedEvidence,
)
from packages.domain.transcript import SpeakerType, TranscriptSegment
from packages.evaluation.base import BaseCheckEvaluator, EvaluatorContext
from packages.evaluation.comparators import (
    ComparatorType,
    ComparisonOutcome,
    coerce_decimal,
    compare_values,
    extract_boolean,
    extract_dates,
    extract_emails,
    extract_identifiers,
    extract_spoken_numbers,
    resolve_expected_value,
)

CORRECTION_MARKERS = (
    "sorry",
    "i mean",
    "i meant",
    "actually",
    "correction",
    "my mistake",
    "let me correct",
    "apologies",
    "rather",
)

# Comparators inferred from the check code when a version omits an explicit one.
_CODE_COMPARATOR_HINTS: tuple[tuple[tuple[str, ...], ComparatorType], ...] = (
    (("EMAIL",), ComparatorType.EMAIL),
    (("DOB", "BIRTH", "DATE", "MOVE_IN"), ComparatorType.DATE),
    (("NMI", "MIRN", "METER"), ComparatorType.IDENTIFIER),
    (("CONCESSION", "LIFE_SUPPORT", "CONSENT_FLAG"), ComparatorType.BOOLEAN),
    (("GIFT_CARD", "PRICE", "COST", "AMOUNT", "MONTHLY"), ComparatorType.MONEY),
    (("RATE", "TARIFF", "CHARGE", "SUPPLY", "DISCOUNT"), ComparatorType.DECIMAL),
    (("ADDRESS", "NAME", "FUEL", "PLAN"), ComparatorType.TEXT),
)

# Near-miss handling per comparator. Email and meter identifiers are delivery-critical: a single
# wrong character is a genuine compliance failure, not a transcription artefact. Free text is the
# opposite — a near match is far more likely a mishear, so a human adjudicates instead.
_DEFAULT_NEAR_MISS_OUTCOME: dict[ComparatorType, CheckOutcome] = {
    ComparatorType.EMAIL: CheckOutcome.FAIL,
    ComparatorType.IDENTIFIER: CheckOutcome.FAIL,
    ComparatorType.TEXT: CheckOutcome.AMBIGUOUS,
}


def _is_explicit_correction(text: str) -> bool:
    return _last_correction_marker(text) is not None


def _last_correction_marker(text: str) -> int | None:
    """Character offset of the last explicit correction marker in the text, if any."""
    lowered = text.lower()
    offsets = [lowered.rfind(marker) for marker in CORRECTION_MARKERS]
    latest = max(offsets)
    return latest if latest >= 0 else None


def _resolve_comparator(check: ResolvedCheck, params: dict[str, Any]) -> ComparatorType:
    declared = params.get("comparator")
    if declared:
        try:
            return ComparatorType(str(declared).upper())
        except ValueError:
            pass
    code = check.check_code.upper()
    for tokens, comparator in _CODE_COMPARATOR_HINTS:
        if any(token in code for token in tokens):
            return comparator
    return ComparatorType.TEXT


def _candidate_paths(params: dict[str, Any]) -> list[str]:
    paths = params.get("crm_fields") or params.get("crm_field")
    if isinstance(paths, str):
        return [paths]
    if isinstance(paths, (list, tuple)):
        return [str(p) for p in paths]
    return []


class FactualMatchEvaluator(BaseCheckEvaluator):
    """Compares spoken values against the authoritative CRM sale and lead snapshot."""

    def can_evaluate(self, check: ResolvedCheck) -> bool:
        return check.check_type == "FACTUAL_MATCH" or check.check_code.startswith("FACTUAL_")

    def evaluate(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
    ) -> CheckExecutionResult:
        params = check.parameters or {}
        comparator = _resolve_comparator(check, params)

        expected_value, expected_source = self._resolve_expected(check, context, params)
        if expected_value is None:
            return self._not_evaluable(
                check,
                "FACTUAL_EXPECTED_VALUE_UNRESOLVED",
            )

        segments = self._scope_segments(context, params)
        candidates = self._extract_candidates(comparator, segments, params, expected_value)

        if not candidates:
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=CheckOutcome.FAIL,
                confidence=1.0,
                score_numeric=0.0,
                evidences=[],
                reason_codes=["VALUE_NOT_DISCLOSED"],
            )

        considered, superseded = self._apply_corrections(candidates, comparator, params)

        tolerance = coerce_decimal(params.get("tolerance", "0")) or Decimal("0")
        near_miss_threshold = float(params.get("near_miss_threshold", 0.85))

        scored = [
            (
                segment,
                observed,
                compare_values(
                    comparator,
                    expected_value,
                    observed,
                    tolerance=tolerance,
                    near_miss_threshold=near_miss_threshold,
                ),
            )
            for segment, observed, _ in considered
        ]

        match = next((entry for entry in scored if entry[2].matched), None)
        chosen = match or max(scored, key=lambda entry: entry[2].similarity)
        segment, observed, comparison = chosen

        evidences = self._build_evidence(
            comparator=comparator,
            expected_value=expected_value,
            expected_source=expected_source,
            chosen=chosen,
            # Free-text scoping pulls in whole utterances that merely mention a keyword; listing
            # them all as evidence would bury the one line that actually decided the check.
            scored=[chosen] if comparator is ComparatorType.TEXT else scored,
            superseded=superseded,
        )

        # Only genuinely competing claims lower confidence. For free text most in-scope segments
        # simply do not contain the CRM value and are noise, not a second version of the answer.
        distinct_values = (
            1
            if comparator is ComparatorType.TEXT
            else len({str(observed) for _, observed, _ in considered})
        )

        return self._finalize(
            check=check,
            comparator=comparator,
            comparison=comparison,
            matched=match is not None,
            candidate_count=distinct_values,
            params=params,
            evidences=evidences,
        )

    # ------------------------------------------------------------------
    # Expected value resolution
    # ------------------------------------------------------------------

    def _resolve_expected(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
        params: dict[str, Any],
    ) -> tuple[Any, str | None]:
        """Resolve the authoritative expected value, or (None, None) if unresolvable."""
        literal = params.get("expected_value")
        if literal is not None and literal != "":
            return literal, "CHECK_VERSION_PARAMETERS"

        paths = _candidate_paths(params)
        if not paths:
            return None, None

        sources: list[tuple[str, Any]] = [
            ("SALE_SNAPSHOT", context.snapshot.sale_snapshot),
            ("LEAD_SNAPSHOT", context.snapshot.lead_snapshot),
            ("SALE_RECORD", context.sale_data),
            ("LEAD_RECORD", context.lead_data),
        ]
        # A bare field name should also resolve one level down into the sale detail payload.
        expanded = list(paths) + [f"details.{p}" for p in paths if "." not in p]
        return resolve_expected_value(sources, expanded)

    # ------------------------------------------------------------------
    # Candidate extraction
    # ------------------------------------------------------------------

    def _scope_segments(
        self,
        context: EvaluatorContext,
        params: dict[str, Any],
    ) -> list[TranscriptSegment]:
        ordered = sorted(context.segments, key=lambda s: (s.start_ms, s.end_ms))

        question_keywords = [str(k).lower() for k in params.get("question_keywords", [])]
        if question_keywords:
            return self._answers_to_questions(ordered, question_keywords, params)

        speaker = str(params.get("speaker", "AGENT")).upper()
        if speaker == "ANY":
            segments = ordered
        else:
            target = SpeakerType.CUSTOMER if speaker == "CUSTOMER" else SpeakerType.AGENT
            segments = [s for s in ordered if s.business_role == target]

        keywords = [str(k).lower() for k in params.get("keywords", [])]
        if keywords:
            segments = [s for s in segments if any(k in s.text.lower() for k in keywords)]
        return segments

    def _answers_to_questions(
        self,
        ordered: list[TranscriptSegment],
        question_keywords: list[str],
        params: dict[str, Any],
    ) -> list[TranscriptSegment]:
        """Scope to the customer's replies to a specific agent question.

        Confirmation checks ask the agent's question and read the answer from the customer's next
        turn, because the answer itself ("no, nobody") carries none of the question's keywords.
        """
        window_ms = int(params.get("response_window_ms", 30_000))
        answer_role = (
            SpeakerType.AGENT
            if str(params.get("answer_speaker", "CUSTOMER")).upper() == "AGENT"
            else SpeakerType.CUSTOMER
        )
        ask_role = SpeakerType.CUSTOMER if answer_role == SpeakerType.AGENT else SpeakerType.AGENT

        answers: list[TranscriptSegment] = []
        for index, segment in enumerate(ordered):
            if segment.business_role != ask_role:
                continue
            if not any(keyword in segment.text.lower() for keyword in question_keywords):
                continue
            for candidate in ordered[index + 1 :]:
                if candidate.start_ms > segment.end_ms + window_ms:
                    break
                if candidate.business_role == answer_role:
                    answers.append(candidate)
                    break
        return answers

    def _extract_candidates(
        self,
        comparator: ComparatorType,
        segments: Sequence[TranscriptSegment],
        params: dict[str, Any],
        expected_value: Any,
    ) -> list[tuple[TranscriptSegment, Any, bool]]:
        """Return (segment, observed_value, is_correction) triples in transcript order.

        A correction marker splits its own segment: values spoken before it are what the agent is
        retracting, values after it are the correction. Treating the whole utterance as one block
        would leave the retracted value competing with the corrected one.
        """
        candidates: list[tuple[TranscriptSegment, Any, bool]] = []

        for segment in segments:
            marker_at = _last_correction_marker(segment.text)
            if marker_at is None:
                candidates.extend(
                    (segment, value, False)
                    for value in self._extract_from_text(comparator, segment.text, params)
                )
                continue

            candidates.extend(
                (segment, value, False)
                for value in self._extract_from_text(
                    comparator, segment.text[:marker_at], params
                )
            )
            candidates.extend(
                (segment, value, True)
                for value in self._extract_from_text(
                    comparator, segment.text[marker_at:], params
                )
            )

        return candidates

    def _apply_corrections(
        self,
        candidates: list[tuple[TranscriptSegment, Any, bool]],
        comparator: ComparatorType,
        params: dict[str, Any],
    ) -> tuple[
        list[tuple[TranscriptSegment, Any, bool]],
        list[tuple[TranscriptSegment, Any, bool]],
    ]:
        """Split candidates into those still standing and those a correction retracted.

        A correction only retracts the statement it is correcting: the values spoken earlier in
        the same breath, or in the utterance immediately before it. It does not invalidate facts
        confirmed elsewhere in the call. Free text is exempt entirely — its observed value is a
        whole utterance, so "sorry, I mean" about a rate would otherwise wipe out an address
        confirmed two minutes earlier.
        """
        corrections = [c for c in candidates if c[2]]
        if not corrections or comparator is ComparatorType.TEXT:
            return list(candidates), []

        window_ms = int(params.get("correction_window_ms", 30_000))
        correction_segment_ids = {segment.id for segment, _, _ in corrections}
        latest_correction_start = max(segment.start_ms for segment, _, _ in corrections)

        considered: list[tuple[TranscriptSegment, Any, bool]] = []
        superseded: list[tuple[TranscriptSegment, Any, bool]] = []

        for candidate in candidates:
            segment, _, is_correction = candidate
            same_breath = segment.id in correction_segment_ids
            immediately_before = 0 <= latest_correction_start - segment.end_ms <= window_ms
            if not is_correction and (same_breath or immediately_before):
                superseded.append(candidate)
            else:
                considered.append(candidate)

        return (considered or corrections), superseded

    def _extract_from_text(
        self,
        comparator: ComparatorType,
        text: str,
        params: dict[str, Any],
    ) -> list[Any]:
        """Extract every observed value of the comparator's kind from a span of speech."""
        if comparator in (ComparatorType.DECIMAL, ComparatorType.MONEY):
            minimum = coerce_decimal(params.get("min_value"))
            maximum = coerce_decimal(params.get("max_value"))
            return [
                number
                for number in extract_spoken_numbers(text)
                if (minimum is None or number >= minimum)
                and (maximum is None or number <= maximum)
            ]
        if comparator is ComparatorType.EMAIL:
            return list(extract_emails(text))
        if comparator is ComparatorType.DATE:
            return list(extract_dates(text))
        if comparator is ComparatorType.IDENTIFIER:
            id_length = params.get("identifier_length", [10, 11])
            return list(extract_identifiers(text, int(id_length[0]), int(id_length[1])))
        if comparator is ComparatorType.BOOLEAN:
            confirmed = extract_boolean(text)
            return [confirmed] if confirmed is not None else []
        return [text] if text.strip() else []

    # ------------------------------------------------------------------
    # Evidence and outcome
    # ------------------------------------------------------------------

    def _build_evidence(
        self,
        comparator: ComparatorType,
        expected_value: Any,
        expected_source: str | None,
        chosen: tuple[TranscriptSegment, Any, ComparisonOutcome],
        scored: list[tuple[TranscriptSegment, Any, ComparisonOutcome]],
        superseded: list[tuple[TranscriptSegment, Any, bool]],
    ) -> list[GroundedEvidence]:
        evidences: list[GroundedEvidence] = []

        for segment, observed, _ in superseded:
            evidences.append(
                GroundedEvidence(
                    transcript_segment_id=segment.id,
                    transcript_id=segment.transcript_id,
                    speaker=segment.business_role.value,
                    evidence_type=EvidenceType.CONTEXT,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    expected_value=str(expected_value),
                    observed_value=str(observed),
                    transcript_excerpt=segment.text,
                    ai_explanation="Superseded by a subsequent explicit verbal correction.",
                    comparison_source=comparator.value,
                    expected_value_source=expected_source,
                    observed_value_source="TRANSCRIPT_SUPERSEDED_STATEMENT",
                )
            )

        chosen_segment, chosen_observed, comparison = chosen
        for segment, observed, other in scored:
            if segment.id == chosen_segment.id and observed == chosen_observed:
                continue
            evidences.append(
                GroundedEvidence(
                    transcript_segment_id=segment.id,
                    transcript_id=segment.transcript_id,
                    speaker=segment.business_role.value,
                    evidence_type=EvidenceType.CONTEXT,
                    start_ms=segment.start_ms,
                    end_ms=segment.end_ms,
                    expected_value=str(expected_value),
                    observed_value=str(observed),
                    transcript_excerpt=segment.text,
                    ai_explanation=f"Additional in-scope value stated. {other.detail}",
                    comparison_source=comparator.value,
                    expected_value_source=expected_source,
                    observed_value_source="TRANSCRIPT_ADDITIONAL_STATEMENT",
                )
            )

        evidences.append(
            GroundedEvidence(
                transcript_segment_id=chosen_segment.id,
                transcript_id=chosen_segment.transcript_id,
                speaker=chosen_segment.business_role.value,
                evidence_type=(
                    EvidenceType.SUPPORTING if comparison.matched else EvidenceType.CONTRADICTING
                ),
                start_ms=chosen_segment.start_ms,
                end_ms=chosen_segment.end_ms,
                expected_value=str(expected_value),
                observed_value=str(chosen_observed),
                transcript_excerpt=chosen_segment.text,
                ai_explanation=comparison.detail,
                comparison_source=comparator.value,
                expected_value_source=expected_source,
                observed_value_source="TRANSCRIPT_AGENT_SPEECH",
            )
        )
        return evidences

    def _finalize(
        self,
        check: ResolvedCheck,
        comparator: ComparatorType,
        comparison: ComparisonOutcome,
        matched: bool,
        candidate_count: int,
        params: dict[str, Any],
        evidences: list[GroundedEvidence],
    ) -> CheckExecutionResult:
        if matched:
            reason_codes = ["FACTUAL_MATCH_VERIFIED"]
            if candidate_count > 1:
                reason_codes.append("MULTIPLE_VALUES_STATED")
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=CheckOutcome.PASS,
                # Several in-scope values were spoken and only one matched; a human confirms.
                confidence=1.0 if candidate_count == 1 else 0.75,
                score_numeric=100.0,
                evidences=evidences,
                reason_codes=reason_codes,
            )

        if comparison.near_miss:
            configured = params.get("near_miss_outcome")
            outcome = (
                CheckOutcome(str(configured).upper())
                if configured
                else _DEFAULT_NEAR_MISS_OUTCOME.get(comparator, CheckOutcome.AMBIGUOUS)
            )
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=outcome,
                confidence=round(comparison.similarity, 2),
                score_numeric=0.0,
                evidences=evidences,
                reason_codes=["FACTUAL_NEAR_MISS_MISMATCH"],
            )

        return CheckExecutionResult(
            check_id=check.check_id,
            check_version_id=check.version_id,
            is_critical=check.is_critical,
            outcome=CheckOutcome.FAIL,
            confidence=1.0,
            score_numeric=0.0,
            evidences=evidences,
            reason_codes=["FACTUAL_MISMATCH"],
        )

    def _not_evaluable(self, check: ResolvedCheck, reason: str) -> CheckExecutionResult:
        return CheckExecutionResult(
            check_id=check.check_id,
            check_version_id=check.version_id,
            is_critical=check.is_critical,
            outcome=CheckOutcome.NOT_EVALUABLE,
            confidence=None,
            score_numeric=None,
            evidences=[],
            reason_codes=[reason],
        )
