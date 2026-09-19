"""Unit tests for the policy governing how AI adjudication may change a check outcome.

These tests pin the safety boundary of "AI proposes; deterministic policy decides": the model can
never rescue a failed critical check, and by default cannot turn an unresolved critical check into
a pass either.
"""

import pytest

from packages.application.ports.adjudicator import (
    AdjudicationRequest,
    AdjudicationVerdict,
    AdjudicationVerdictType,
    AdjudicatorPort,
    NullAdjudicator,
)
from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    EvidenceType,
    GroundedEvidence,
)
from packages.domain.transcript import SpeakerType, TranscriptSegment
from packages.evaluation.policy.adjudication_policy import (
    AdjudicationPolicy,
    AmbiguityAdjudicationService,
)


class StubAdjudicator(AdjudicatorPort):
    """Returns a scripted verdict and records what it was asked."""

    def __init__(self, verdict: AdjudicationVerdict):
        self.verdict = verdict
        self.requests: list[AdjudicationRequest] = []

    def adjudicate(self, request: AdjudicationRequest) -> AdjudicationVerdict:
        self.requests.append(request)
        return self.verdict

    def provider_name(self) -> str:
        return "stub"


def verdict(
    kind: AdjudicationVerdictType,
    confidence: float = 0.95,
    segment_id: str | None = "seg-1",
) -> AdjudicationVerdict:
    return AdjudicationVerdict(
        verdict=kind,
        confidence=confidence,
        rationale="Stubbed rationale.",
        supporting_segment_id=segment_id,
        provider="stub",
        model="stub-model",
        model_version="1.0",
        prompt_version="adjudicator.v1",
    )


def segment(segment_id: str = "seg-1") -> TranscriptSegment:
    return TranscriptSegment.create(
        transcript_id="tx-1",
        segment_order=1,
        business_role=SpeakerType.AGENT,
        start_ms=1000,
        end_ms=6000,
        text="This call is recorded for training and quality purposes.",
        segment_id=segment_id,
    )


def check(is_critical: bool = True) -> ResolvedCheck:
    return ResolvedCheck(
        check_id="chk-1",
        check_code="VERBATIM_RECORDING_DISCLAIMER",
        name="Call Recording Disclosure",
        check_type="VERBATIM",
        is_critical=is_critical,
        weight=10,
        version_id="chk-1-v1",
        version_number=1,
        parameters={"required_phrases": ["This call is being recorded."]},
        jurisdiction="AU-VIC",
        regulatory_reference="Privacy Act 1988 (Cth) APP 5",
        rule_type="LEGAL_REQUIREMENT",
    )


def result(outcome: CheckOutcome, is_critical: bool = True) -> CheckExecutionResult:
    return CheckExecutionResult(
        check_id="chk-1",
        check_version_id="chk-1-v1",
        is_critical=is_critical,
        outcome=outcome,
        confidence=0.72,
        score_numeric=72.0,
        evidences=[
            GroundedEvidence(
                transcript_segment_id="seg-1",
                transcript_id="tx-1",
                speaker="AGENT",
                evidence_type=EvidenceType.CONTRADICTING,
                start_ms=1000,
                end_ms=6000,
                expected_value="This call is being recorded.",
                observed_value="This call is recorded for training and quality purposes.",
                transcript_excerpt="This call is recorded for training and quality purposes.",
                ai_explanation="Partial verbatim match.",
            )
        ],
        reason_codes=["VERBATIM_PARTIAL_OR_AMBIGUOUS_MATCH"],
    )


def run(
    service: AmbiguityAdjudicationService,
    check_result: CheckExecutionResult,
    resolved: ResolvedCheck,
) -> CheckExecutionResult:
    segments = [segment()]
    return service.adjudicate_results(
        results=[check_result],
        resolved_checks_by_id={resolved.check_id: resolved},
        segments_by_id={s.id: s for s in segments},
        all_segments=segments,
    )[0]


class TestEligibility:
    @pytest.mark.parametrize(
        "outcome",
        [
            CheckOutcome.PASS,
            CheckOutcome.FAIL,
            CheckOutcome.NOT_EVALUABLE,
            CheckOutcome.UNSUPPORTED,
        ],
    )
    def test_settled_outcomes_are_never_revisited(self, outcome):
        """A model must not be able to overturn a deterministic verdict in either direction."""
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.SATISFIED))
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(service, result(outcome), check())

        assert adjudicated.outcome == outcome
        assert adjudicator.requests == []

    def test_ambiguous_findings_are_offered_to_the_adjudicator(self):
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.NOT_SATISFIED))
        service = AmbiguityAdjudicationService(adjudicator)

        run(service, result(CheckOutcome.AMBIGUOUS), check())

        assert len(adjudicator.requests) == 1
        assert adjudicator.requests[0].check_code == "VERBATIM_RECORDING_DISCLAIMER"
        assert adjudicator.requests[0].segments[0].segment_id == "seg-1"


class TestCriticalUpgradeProtection:
    def test_critical_check_is_not_upgraded_to_pass_by_default(self):
        """The one move that could ship a non-compliant sale stays with a human."""
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.SATISFIED, 0.99))
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(service, result(CheckOutcome.AMBIGUOUS), check(is_critical=True))

        assert adjudicated.outcome == CheckOutcome.AMBIGUOUS
        assert "ADJUDICATION_PASS_WITHHELD_ON_CRITICAL" in adjudicated.reason_codes

    def test_critical_upgrade_is_possible_only_when_explicitly_enabled(self):
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.SATISFIED, 0.99))
        service = AmbiguityAdjudicationService(
            adjudicator,
            AdjudicationPolicy(allow_upgrade_to_pass_on_critical=True),
        )

        adjudicated = run(service, result(CheckOutcome.AMBIGUOUS), check(is_critical=True))

        assert adjudicated.outcome == CheckOutcome.PASS
        assert "ADJUDICATED_SATISFIED" in adjudicated.reason_codes

    def test_non_critical_check_may_be_resolved_to_pass(self):
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.SATISFIED, 0.99))
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(
            service,
            result(CheckOutcome.AMBIGUOUS, is_critical=False),
            check(is_critical=False),
        )

        assert adjudicated.outcome == CheckOutcome.PASS

    def test_critical_check_may_always_be_resolved_to_fail(self):
        """Making an outcome stricter is always permitted; it cannot ship a bad sale."""
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.NOT_SATISFIED, 0.99))
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(service, result(CheckOutcome.AMBIGUOUS), check(is_critical=True))

        assert adjudicated.outcome == CheckOutcome.FAIL
        assert adjudicated.score_numeric == 0.0
        assert "ADJUDICATED_NOT_SATISFIED" in adjudicated.reason_codes


class TestConfidenceAndDegradation:
    def test_low_confidence_proposal_is_not_applied(self):
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.NOT_SATISFIED, 0.40))
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(service, result(CheckOutcome.AMBIGUOUS), check())

        assert adjudicated.outcome == CheckOutcome.AMBIGUOUS
        assert "ADJUDICATION_BELOW_CONFIDENCE_THRESHOLD" in adjudicated.reason_codes

    def test_cannot_determine_leaves_the_finding_for_a_human(self):
        adjudicator = StubAdjudicator(
            AdjudicationVerdict(
                verdict=AdjudicationVerdictType.CANNOT_DETERMINE,
                confidence=0.0,
                rationale="Transcript is garbled.",
                provider="stub",
                model="stub-model",
            )
        )
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(service, result(CheckOutcome.AMBIGUOUS), check())

        assert adjudicated.outcome == CheckOutcome.AMBIGUOUS
        assert "ADJUDICATION_UNRESOLVED" in adjudicated.reason_codes

    def test_no_adjudicator_configured_leaves_results_untouched(self):
        service = AmbiguityAdjudicationService(NullAdjudicator())
        original = result(CheckOutcome.AMBIGUOUS)

        adjudicated = run(service, original, check())

        assert adjudicated.outcome == CheckOutcome.AMBIGUOUS
        assert adjudicated.reason_codes == original.reason_codes


class TestEvidenceProvenance:
    def test_resolved_outcome_records_the_model_that_proposed_it(self):
        adjudicator = StubAdjudicator(verdict(AdjudicationVerdictType.NOT_SATISFIED, 0.99))
        service = AmbiguityAdjudicationService(adjudicator)

        adjudicated = run(service, result(CheckOutcome.AMBIGUOUS), check())
        evidence = adjudicated.evidences[-1]

        assert evidence.comparison_source == "AI_ADJUDICATION"
        assert evidence.observed_value_source == "stub:stub-model"
        assert "adjudicator.v1" in evidence.ai_explanation
        # Still grounded to a playable moment in the call.
        assert evidence.start_ms == 1000
        assert evidence.transcript_segment_id == "seg-1"
