"""Unit tests for the Tier C behaviour evaluator across all five coaching metrics."""

import pytest

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import CheckOutcome, EvaluationInputSnapshot
from packages.domain.transcript import SpeakerType, TranscriptSegment
from packages.evaluation.base import EvaluatorContext
from packages.evaluation.evaluators.behavior import BehaviorEvaluator

TRANSCRIPT_ID = "tx-behaviour"


def segment(order: int, role: SpeakerType, start_ms: int, end_ms: int, text: str = "word " * 20):
    return TranscriptSegment.create(
        transcript_id=TRANSCRIPT_ID,
        segment_order=order,
        business_role=role,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        segment_id=f"seg-{order}",
    )


def make_check(check_code: str, parameters: dict) -> ResolvedCheck:
    return ResolvedCheck(
        check_id=f"chk-{check_code.lower()}",
        check_code=check_code,
        name=check_code,
        check_type="BEHAVIOUR",
        is_critical=False,
        weight=3,
        version_id=f"{check_code}-v1",
        version_number=1,
        parameters=parameters,
        jurisdiction="AU-VIC",
        regulatory_reference=None,
        rule_type="INTERNAL_QA_STANDARD",
    )


def make_context(segments) -> EvaluatorContext:
    snapshot = EvaluationInputSnapshot.create(
        sale_id="sale-1",
        tenant_id="tenant-1",
        transcript_id=TRANSCRIPT_ID,
        transcript_version_id="v1",
        transcript_content_hash="hash",
        audio_artifact_hash="audio",
        sale_snapshot={},
        lead_snapshot={},
        resolved_check_snapshots=[],
        policy_version="policy.v1",
        evaluator_config_hash="cfg",
    )
    return EvaluatorContext(snapshot=snapshot, segments=segments, sale_data={}, lead_data={})


class TestDeadAir:
    def test_gap_beyond_threshold_fails_with_exact_span(self):
        check = make_check("BEHAVIOUR_DEAD_AIR", {"max_silence_threshold_ms": 30000})
        segments = [
            segment(1, SpeakerType.AGENT, 1_080_000, 1_083_000),
            segment(2, SpeakerType.CUSTOMER, 1_130_000, 1_135_000),
        ]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["EXCESSIVE_DEAD_AIR"]
        assert result.evidences[0].start_ms == 1_083_000
        assert result.evidences[0].end_ms == 1_130_000

    def test_gap_within_threshold_passes(self):
        check = make_check("BEHAVIOUR_DEAD_AIR", {"max_silence_threshold_ms": 60000})
        segments = [
            segment(1, SpeakerType.AGENT, 1_080_000, 1_083_000),
            segment(2, SpeakerType.CUSTOMER, 1_130_000, 1_135_000),
        ]

        assert (
            BehaviorEvaluator().evaluate(check, make_context(segments)).outcome
            == CheckOutcome.PASS
        )

    def test_behaviour_checks_are_never_critical_so_never_block(self):
        check = make_check("BEHAVIOUR_DEAD_AIR", {"max_silence_threshold_ms": 1000})
        segments = [
            segment(1, SpeakerType.AGENT, 0, 1000),
            segment(2, SpeakerType.CUSTOMER, 60_000, 61_000),
        ]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.FAIL
        assert result.is_critical is False


class TestInterruptions:
    def test_agent_talking_over_customer_beyond_allowance_fails(self):
        check = make_check(
            "BEHAVIOUR_INTERRUPTIONS",
            {"max_interruptions": 1, "overlap_tolerance_ms": 300},
        )
        segments = [
            segment(1, SpeakerType.CUSTOMER, 0, 10_000),
            segment(2, SpeakerType.AGENT, 2_000, 4_000),
            segment(3, SpeakerType.CUSTOMER, 12_000, 20_000),
            segment(4, SpeakerType.AGENT, 14_000, 16_000),
            segment(5, SpeakerType.CUSTOMER, 22_000, 30_000),
            segment(6, SpeakerType.AGENT, 24_000, 26_000),
        ]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["EXCESSIVE_INTERRUPTIONS"]

    def test_clean_turn_taking_passes(self):
        check = make_check("BEHAVIOUR_INTERRUPTIONS", {"max_interruptions": 3})
        segments = [
            segment(1, SpeakerType.AGENT, 0, 5_000),
            segment(2, SpeakerType.CUSTOMER, 5_500, 9_000),
        ]

        assert (
            BehaviorEvaluator().evaluate(check, make_context(segments)).outcome
            == CheckOutcome.PASS
        )


class TestTalkRatio:
    def test_agent_dominating_the_call_falls_outside_band(self):
        check = make_check(
            "BEHAVIOUR_TALK_RATIO", {"min_agent_ratio": 0.35, "max_agent_ratio": 0.70}
        )
        segments = [
            segment(1, SpeakerType.AGENT, 0, 90_000),
            segment(2, SpeakerType.CUSTOMER, 90_000, 100_000),
        ]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["TALK_RATIO_OUT_OF_BAND"]

    def test_balanced_conversation_passes(self):
        check = make_check(
            "BEHAVIOUR_TALK_RATIO", {"min_agent_ratio": 0.35, "max_agent_ratio": 0.85}
        )
        segments = [
            segment(1, SpeakerType.AGENT, 0, 50_000),
            segment(2, SpeakerType.CUSTOMER, 50_000, 100_000),
        ]

        assert (
            BehaviorEvaluator().evaluate(check, make_context(segments)).outcome
            == CheckOutcome.PASS
        )


class TestSpeechRate:
    def test_speech_rate_outside_band_fails(self):
        check = make_check("BEHAVIOUR_SPEECH_RATE", {"min_wpm": 110, "max_wpm": 200})
        # 20 words spoken across 60 seconds is 20 wpm.
        segments = [segment(1, SpeakerType.AGENT, 0, 60_000, text="word " * 20)]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["SPEECH_RATE_OUT_OF_BAND"]

    def test_speech_rate_inside_band_passes(self):
        check = make_check("BEHAVIOUR_SPEECH_RATE", {"min_wpm": 110, "max_wpm": 200})
        # 150 words across 60 seconds is 150 wpm.
        segments = [segment(1, SpeakerType.AGENT, 0, 60_000, text="word " * 150)]

        assert (
            BehaviorEvaluator().evaluate(check, make_context(segments)).outcome
            == CheckOutcome.PASS
        )


class TestObjectionHandling:
    PARAMS = {
        "metric": "OBJECTION_HANDLING",
        "objection_markers": ["not interested", "too expensive"],
        "acknowledgement_markers": ["i understand", "i appreciate"],
        "response_window_ms": 30_000,
    }

    def test_unacknowledged_objection_fails_and_cites_the_customer_line(self):
        check = make_check("BEHAVIOUR_OBJECTION_HANDLING", self.PARAMS)
        segments = [
            segment(1, SpeakerType.CUSTOMER, 10_000, 13_000, "I'm not interested thanks"),
            segment(2, SpeakerType.AGENT, 14_000, 18_000, "So the peak rate is 31.9 cents"),
        ]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["UNHANDLED_OBJECTION"]
        assert result.evidences[0].start_ms == 10_000

    def test_acknowledged_objection_passes(self):
        check = make_check("BEHAVIOUR_OBJECTION_HANDLING", self.PARAMS)
        segments = [
            segment(1, SpeakerType.CUSTOMER, 10_000, 13_000, "that is too expensive"),
            segment(2, SpeakerType.AGENT, 14_000, 18_000, "I understand, let me explain"),
        ]

        assert (
            BehaviorEvaluator().evaluate(check, make_context(segments)).outcome
            == CheckOutcome.PASS
        )

    def test_acknowledgement_outside_response_window_does_not_count(self):
        check = make_check("BEHAVIOUR_OBJECTION_HANDLING", self.PARAMS)
        segments = [
            segment(1, SpeakerType.CUSTOMER, 10_000, 13_000, "that is too expensive"),
            segment(2, SpeakerType.AGENT, 90_000, 94_000, "I understand"),
        ]

        assert (
            BehaviorEvaluator().evaluate(check, make_context(segments)).outcome
            == CheckOutcome.FAIL
        )

    def test_call_without_objections_passes(self):
        check = make_check("BEHAVIOUR_OBJECTION_HANDLING", self.PARAMS)
        segments = [segment(1, SpeakerType.CUSTOMER, 0, 4_000, "that sounds good")]

        result = BehaviorEvaluator().evaluate(check, make_context(segments))

        assert result.outcome == CheckOutcome.PASS
        assert result.reason_codes == ["NO_OBJECTIONS_RAISED"]


@pytest.mark.parametrize(
    "check_code,metric",
    [
        ("BEHAVIOUR_DEAD_AIR", "DEAD_AIR"),
        ("BEHAVIOUR_INTERRUPTIONS", "INTERRUPTIONS"),
        ("BEHAVIOUR_TALK_RATIO", "TALK_RATIO"),
        ("BEHAVIOUR_OBJECTION_HANDLING", "OBJECTION_HANDLING"),
        ("BEHAVIOUR_SPEECH_RATE", "SPEECH_RATE"),
    ],
)
def test_every_catalogued_behaviour_metric_is_dispatchable(check_code, metric):
    """No behaviour check in the shipped checklist may fall through as unsupported."""
    check = make_check(check_code, {"metric": metric, "objection_markers": ["no"]})
    segments = [
        segment(1, SpeakerType.AGENT, 0, 30_000, text="word " * 75),
        segment(2, SpeakerType.CUSTOMER, 30_000, 50_000, text="word " * 40),
    ]

    result = BehaviorEvaluator().evaluate(check, make_context(segments))

    assert result.outcome != CheckOutcome.UNSUPPORTED
