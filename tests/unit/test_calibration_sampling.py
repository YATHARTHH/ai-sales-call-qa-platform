"""Unit tests for deterministic calibration sampling of otherwise-clean calls."""

from packages.application.services.check_resolver import ResolvedCheck
from packages.application.services.transcript_validator import TranscriptIntegrityResult
from packages.domain.evaluation import CheckExecutionResult, CheckOutcome, GateReasonCode
from packages.domain.state import GateStatus
from packages.evaluation.policy.gate_engine import DeterministicPolicyEngine
from packages.evaluation.policy.score_calculator import ScoreCalculationResult

VALID_TRANSCRIPT = TranscriptIntegrityResult(is_valid=True, reason_codes=[])
CLEAN_SCORE = ScoreCalculationResult(
    overall_score=100.0, eligible_check_count=1, total_eligible_weight=10, is_scoreable=True
)


def passing_check() -> CheckExecutionResult:
    return CheckExecutionResult(
        check_id="chk-1",
        check_version_id="chk-1-v1",
        is_critical=True,
        outcome=CheckOutcome.PASS,
        confidence=1.0,
        score_numeric=100.0,
    )


def resolved_check() -> ResolvedCheck:
    return ResolvedCheck(
        check_id="chk-1",
        check_code="VERBATIM_TEST",
        name="Test",
        check_type="VERBATIM",
        is_critical=True,
        weight=10,
        version_id="chk-1-v1",
        version_number=1,
        parameters={},
        jurisdiction="AU-VIC",
        regulatory_reference=None,
        rule_type="LEGAL_REQUIREMENT",
    )


def evaluate(sale_id: str, sample_rate: float):
    return DeterministicPolicyEngine.evaluate_gate(
        sale_id=sale_id,
        evaluation_run_id="run-1",
        transcript_integrity=VALID_TRANSCRIPT,
        check_results=[passing_check()],
        resolved_checks=[resolved_check()],
        score_result=CLEAN_SCORE,
        clean_call_sample_rate=sample_rate,
    )


class TestSamplingSelection:
    def test_selection_is_deterministic_for_a_given_sale(self):
        first = DeterministicPolicyEngine.is_sampled_for_calibration("sale-42", "policy.v1", 0.05)
        second = DeterministicPolicyEngine.is_sampled_for_calibration("sale-42", "policy.v1", 0.05)

        assert first == second

    def test_rate_of_zero_never_samples(self):
        assert not any(
            DeterministicPolicyEngine.is_sampled_for_calibration(f"sale-{i}", "policy.v1", 0.0)
            for i in range(200)
        )

    def test_rate_of_one_always_samples(self):
        assert all(
            DeterministicPolicyEngine.is_sampled_for_calibration(f"sale-{i}", "policy.v1", 1.0)
            for i in range(50)
        )

    def test_observed_rate_approximates_the_configured_rate(self):
        sampled = sum(
            DeterministicPolicyEngine.is_sampled_for_calibration(
                f"sale-{i}", "policy.v1", 0.05
            )
            for i in range(20_000)
        )
        observed = sampled / 20_000

        assert 0.04 <= observed <= 0.06

    def test_policy_version_changes_the_sampled_population(self):
        v1 = {
            i
            for i in range(2_000)
            if DeterministicPolicyEngine.is_sampled_for_calibration(
                f"sale-{i}", "policy.v1", 0.05
            )
        }
        v2 = {
            i
            for i in range(2_000)
            if DeterministicPolicyEngine.is_sampled_for_calibration(
                f"sale-{i}", "policy.v2", 0.05
            )
        }

        assert v1 != v2


class TestGateIntegration:
    def test_sampled_clean_call_routes_to_human_and_does_not_auto_submit(self):
        decision = evaluate("sale-always-sampled", sample_rate=1.0)

        assert decision.status == GateStatus.REVIEW_REQUIRED
        assert decision.decision_reason_code == GateReasonCode.SAMPLED_FOR_CALIBRATION.value
        assert decision.auto_submitted is False
        assert "ALL_CRITICAL_CHECKS_PASSED" in decision.reason_codes

    def test_unsampled_clean_call_still_auto_submits(self):
        decision = evaluate("sale-never-sampled", sample_rate=0.0)

        assert decision.status == GateStatus.PASSED
        assert decision.auto_submitted is True

    def test_sampling_never_overturns_a_critical_failure(self):
        """Sampling must sit below every blocking condition in the precedence table."""
        failing = CheckExecutionResult(
            check_id="chk-1",
            check_version_id="chk-1-v1",
            is_critical=True,
            outcome=CheckOutcome.FAIL,
            confidence=1.0,
            score_numeric=0.0,
        )

        decision = DeterministicPolicyEngine.evaluate_gate(
            sale_id="sale-1",
            evaluation_run_id="run-1",
            transcript_integrity=VALID_TRANSCRIPT,
            check_results=[failing],
            resolved_checks=[resolved_check()],
            score_result=CLEAN_SCORE,
            clean_call_sample_rate=1.0,
        )

        assert decision.status == GateStatus.HELD
        assert decision.decision_reason_code == GateReasonCode.CRITICAL_CHECK_FAILED.value
