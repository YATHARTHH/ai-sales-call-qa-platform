"""Unit tests for the parameter-driven Tier B factual evaluator.

These tests pin the guarantee that matters most under audit: the evaluator never invents an
expected value, and a critical check whose CRM field cannot be resolved must not silently pass.
"""

import pytest

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import CheckOutcome, EvaluationInputSnapshot, EvidenceType
from packages.domain.transcript import SpeakerType, TranscriptSegment
from packages.evaluation.base import EvaluatorContext
from packages.evaluation.evaluators.factual import FactualMatchEvaluator

TRANSCRIPT_ID = "tx-test"


def segment(order: int, role: SpeakerType, text: str, start_ms: int = 0, end_ms: int = 5000):
    return TranscriptSegment.create(
        transcript_id=TRANSCRIPT_ID,
        segment_order=order,
        business_role=role,
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        segment_id=f"seg-{order}",
    )


def make_check(check_code: str, parameters: dict, is_critical: bool = True) -> ResolvedCheck:
    return ResolvedCheck(
        check_id=f"chk-{check_code.lower()}",
        check_code=check_code,
        name=check_code,
        check_type="FACTUAL_MATCH",
        is_critical=is_critical,
        weight=10,
        version_id=f"{check_code}-v1",
        version_number=1,
        parameters=parameters,
        jurisdiction="AU-VIC",
        regulatory_reference=None,
        rule_type="LEGAL_REQUIREMENT",
    )


def make_context(segments, sale_data=None, lead_data=None) -> EvaluatorContext:
    sale_data = sale_data or {}
    lead_data = lead_data or {}
    snapshot = EvaluationInputSnapshot.create(
        sale_id="sale-1",
        tenant_id="tenant-1",
        transcript_id=TRANSCRIPT_ID,
        transcript_version_id="v1",
        transcript_content_hash="hash",
        audio_artifact_hash="audio",
        sale_snapshot=sale_data,
        lead_snapshot=lead_data,
        resolved_check_snapshots=[],
        policy_version="policy.v1",
        evaluator_config_hash="cfg",
    )
    return EvaluatorContext(
        snapshot=snapshot,
        segments=segments,
        sale_data=sale_data,
        lead_data=lead_data,
    )


class TestExpectedValueResolution:
    def test_unresolvable_crm_field_is_not_evaluable_never_pass(self):
        """The critical guarantee: no CRM value means no verdict, so the gate holds the sale."""
        check = make_check("FACTUAL_PEAK_RATE", {"crm_field": "details.tariff_peak_c_kwh"})
        context = make_context(
            [segment(1, SpeakerType.AGENT, "your peak rate is 28.6 cents")],
            sale_data={"details": {}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.NOT_EVALUABLE
        assert result.reason_codes == ["FACTUAL_EXPECTED_VALUE_UNRESOLVED"]
        assert result.score_numeric is None

    def test_check_without_any_crm_field_is_not_evaluable(self):
        check = make_check("FACTUAL_PEAK_RATE", {})
        context = make_context([segment(1, SpeakerType.AGENT, "the rate is 28.6 cents")])

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.NOT_EVALUABLE

    def test_expected_value_records_its_source_in_evidence(self):
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {"crm_field": "details.tariff_peak_c_kwh", "keywords": ["rate"]},
        )
        context = make_context(
            [segment(1, SpeakerType.AGENT, "your peak rate is 31.9 cents")],
            sale_data={"details": {"tariff_peak_c_kwh": 31.9}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.PASS
        assert result.evidences[0].expected_value_source == "SALE_SNAPSHOT.details.tariff_peak_c_kwh"


class TestRateComparison:
    def test_quoted_rate_below_plan_rate_fails_with_timestamped_evidence(self):
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {
                "crm_field": "details.tariff_peak_c_kwh",
                "keywords": ["rate", "cent"],
                "min_value": "5",
                "max_value": "500",
            },
        )
        context = make_context(
            [segment(1, SpeakerType.AGENT, "your peak rate is 28.6 cents", 842000, 848000)],
            sale_data={"details": {"tariff_peak_c_kwh": 31.9}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["FACTUAL_MISMATCH"]
        evidence = result.evidences[-1]
        assert evidence.evidence_type == EvidenceType.CONTRADICTING
        assert evidence.start_ms == 842000
        assert evidence.observed_value == "28.6"
        assert evidence.expected_value == "31.9"

    def test_spoken_word_rate_is_compared_correctly(self):
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {"crm_field": "details.tariff_peak_c_kwh", "keywords": ["rate"]},
        )
        context = make_context(
            [segment(1, SpeakerType.AGENT, "your peak rate is thirty one point nine cents")],
            sale_data={"details": {"tariff_peak_c_kwh": "31.9"}},
        )

        assert FactualMatchEvaluator().evaluate(check, context).outcome == CheckOutcome.PASS

    def test_keyword_scope_excludes_unrelated_figures(self):
        """A matching number spoken outside the check's scope must not satisfy the check."""
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {"crm_field": "details.tariff_peak_c_kwh", "keywords": ["peak rate"]},
        )
        context = make_context(
            [
                segment(1, SpeakerType.AGENT, "your account balance is 31.9 dollars", 0, 5000),
                segment(2, SpeakerType.AGENT, "your peak rate is 28.6 cents", 6000, 9000),
            ],
            sale_data={"details": {"tariff_peak_c_kwh": 31.9}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.FAIL

    def test_explicit_verbal_correction_supersedes_earlier_statement(self):
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {"crm_field": "details.tariff_peak_c_kwh", "keywords": ["rate", "cent"]},
        )
        context = make_context(
            [
                segment(1, SpeakerType.AGENT, "your peak rate is 28.6 cents", 0, 5000),
                segment(
                    2, SpeakerType.AGENT, "sorry, I mean the peak rate is 31.9 cents", 6000, 11000
                ),
            ],
            sale_data={"details": {"tariff_peak_c_kwh": 31.9}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.PASS
        superseded = [e for e in result.evidences if e.evidence_type == EvidenceType.CONTEXT]
        assert any(e.observed_value == "28.6" for e in superseded)

    def test_rate_never_disclosed_fails(self):
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {"crm_field": "details.tariff_peak_c_kwh", "keywords": ["rate"]},
        )
        context = make_context(
            [segment(1, SpeakerType.AGENT, "thanks for your time today")],
            sale_data={"details": {"tariff_peak_c_kwh": 31.9}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["VALUE_NOT_DISCLOSED"]


class TestEmailComparison:
    def test_email_typo_fails_as_a_material_mismatch(self):
        check = make_check("FACTUAL_EMAIL_ADDRESS", {"crm_field": "customer_email"})
        context = make_context(
            [segment(1, SpeakerType.AGENT, "I have j.smith@gmail.com", 1330000, 1335000)],
            lead_data={"customer_email": "j.smith@gmial.com"},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.FAIL
        assert result.reason_codes == ["FACTUAL_NEAR_MISS_MISMATCH"]
        assert result.evidences[-1].start_ms == 1330000

    def test_matching_email_passes(self):
        check = make_check("FACTUAL_EMAIL_ADDRESS", {"crm_field": "customer_email"})
        context = make_context(
            [segment(1, SpeakerType.AGENT, "I have j.smith@gmail.com")],
            lead_data={"customer_email": "j.smith@gmail.com"},
        )

        assert FactualMatchEvaluator().evaluate(check, context).outcome == CheckOutcome.PASS


class TestTextAndBooleanComparison:
    def test_near_miss_on_free_text_routes_to_human_rather_than_failing(self):
        """Free text near-misses are usually mishears, so a human adjudicates."""
        check = make_check(
            "FACTUAL_CUSTOMER_NAME",
            {"comparator": "TEXT", "crm_field": "customer_name", "keywords": ["speaking"]},
        )
        context = make_context(
            [segment(1, SpeakerType.AGENT, "Jon Smyth speaking")],
            lead_data={"customer_name": "John Smith speaking"},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.AMBIGUOUS

    def test_customer_confirmation_compared_to_crm_flag(self):
        check = make_check(
            "FACTUAL_CONCESSION_STATUS",
            {
                "comparator": "BOOLEAN",
                "crm_field": "details.concession_applied",
                "keywords": ["concession"],
                "speaker": "CUSTOMER",
            },
        )
        context = make_context(
            [segment(1, SpeakerType.CUSTOMER, "no concession card for me")],
            sale_data={"details": {"concession_applied": False}},
        )

        assert FactualMatchEvaluator().evaluate(check, context).outcome == CheckOutcome.PASS


class TestConfidenceSignalling:
    def test_ambiguous_extraction_lowers_confidence_for_gate_routing(self):
        """Several in-scope values with only one matching is reported as low confidence."""
        check = make_check(
            "FACTUAL_PEAK_RATE",
            {"crm_field": "details.tariff_peak_c_kwh", "keywords": ["rate", "cent"]},
        )
        context = make_context(
            [segment(1, SpeakerType.AGENT, "the rate is 31.9 cents or maybe 28.6 cents")],
            sale_data={"details": {"tariff_peak_c_kwh": 31.9}},
        )

        result = FactualMatchEvaluator().evaluate(check, context)

        assert result.outcome == CheckOutcome.PASS
        assert result.confidence < 0.80
        assert "MULTIPLE_VALUES_STATED" in result.reason_codes


@pytest.mark.parametrize(
    "check_code,expected_comparator_behaviour",
    [
        ("FACTUAL_EMAIL_ADDRESS", CheckOutcome.NOT_EVALUABLE),
        ("FACTUAL_NMI", CheckOutcome.NOT_EVALUABLE),
        ("FACTUAL_DATE_OF_BIRTH", CheckOutcome.NOT_EVALUABLE),
    ],
)
def test_every_comparator_family_fails_safe_without_crm_data(
    check_code, expected_comparator_behaviour
):
    check = make_check(check_code, {"crm_field": "nonexistent.path"})
    context = make_context([segment(1, SpeakerType.AGENT, "some speech")])

    assert FactualMatchEvaluator().evaluate(check, context).outcome == (
        expected_comparator_behaviour
    )
