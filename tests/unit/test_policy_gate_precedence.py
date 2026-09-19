"""Table-driven test suite for Deterministic Policy Gate Engine precedence resolution."""

import pytest
from packages.application.services.check_resolver import ResolvedCheck
from packages.application.services.transcript_validator import TranscriptIntegrityResult
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    GateReasonCode,
)
from packages.domain.state import GateStatus
from packages.evaluation.policy.gate_engine import DeterministicPolicyEngine
from packages.evaluation.policy.score_calculator import ScoreCalculationResult


def make_resolved_check(check_id: str, is_critical: bool, weight: int = 10) -> ResolvedCheck:
    return ResolvedCheck(
        check_id=check_id,
        check_code=f"CODE_{check_id}",
        name=f"Check {check_id}",
        check_type="VERBATIM",
        is_critical=is_critical,
        weight=weight,
        version_id=f"v-{check_id}",
        version_number=1,
        parameters={},
        jurisdiction="AU-VIC",
        regulatory_reference=None,
        rule_type="LEGAL_REQUIREMENT",
    )


def make_result(
    check_id: str,
    is_critical: bool,
    outcome: CheckOutcome,
    confidence: float | None = 0.95,
    score: float | None = 100.0,
) -> CheckExecutionResult:
    return CheckExecutionResult(
        check_id=check_id,
        check_version_id=f"v-{check_id}",
        is_critical=is_critical,
        outcome=outcome,
        confidence=confidence,
        score_numeric=score,
    )


# 10 Distinct precedence test cases
test_cases = [
    # 1. Incomplete transcript + critical fail -> HELD (TRANSCRIPT_INCOMPLETE takes precedence)
    (
        TranscriptIntegrityResult(is_valid=False, reason_codes=["TRANSCRIPT_INCOMPLETE"]),
        [make_result("c1", True, CheckOutcome.FAIL)],
        ScoreCalculationResult(overall_score=0.0, eligible_check_count=1, total_eligible_weight=10, is_scoreable=True),
        GateStatus.HELD,
        GateReasonCode.TRANSCRIPT_INCOMPLETE.value,
        False,
        [],
    ),
    # 2. Critical fail + critical ambiguity -> HELD (CRITICAL_CHECK_FAILED takes precedence over ambiguity)
    (
        TranscriptIntegrityResult(is_valid=True),
        [
            make_result("c1", True, CheckOutcome.FAIL),
            make_result("c2", True, CheckOutcome.AMBIGUOUS),
        ],
        ScoreCalculationResult(overall_score=25.0, eligible_check_count=2, total_eligible_weight=20, is_scoreable=True),
        GateStatus.HELD,
        GateReasonCode.CRITICAL_CHECK_FAILED.value,
        False,
        ["c1"],
    ),
    # 3. Critical error + low score -> HELD (CRITICAL_CHECK_EXECUTION_ERROR takes precedence)
    (
        TranscriptIntegrityResult(is_valid=True),
        [make_result("c1", True, CheckOutcome.NOT_EVALUABLE, confidence=None, score=None)],
        ScoreCalculationResult(overall_score=None, eligible_check_count=0, total_eligible_weight=0, is_scoreable=False),
        GateStatus.HELD,
        GateReasonCode.CRITICAL_CHECK_EXECUTION_ERROR.value,
        False,
        ["c1"],
    ),
    # 4. Unsupported critical check + high score -> HELD (UNSUPPORTED_CRITICAL_CHECK)
    (
        TranscriptIntegrityResult(is_valid=True),
        [
            make_result("c1", True, CheckOutcome.UNSUPPORTED, confidence=None, score=None),
            make_result("c2", False, CheckOutcome.PASS, confidence=0.99, score=100.0),
        ],
        ScoreCalculationResult(overall_score=100.0, eligible_check_count=1, total_eligible_weight=10, is_scoreable=True),
        GateStatus.HELD,
        GateReasonCode.UNSUPPORTED_CRITICAL_CHECK.value,
        False,
        ["c1"],
    ),
    # 5. Critical pass + low confidence (0.65) -> REVIEW_REQUIRED (LOW_CONFIDENCE_OR_AMBIGUOUS_FINDING)
    (
        TranscriptIntegrityResult(is_valid=True),
        [make_result("c1", True, CheckOutcome.PASS, confidence=0.65, score=100.0)],
        ScoreCalculationResult(overall_score=100.0, eligible_check_count=1, total_eligible_weight=10, is_scoreable=True),
        GateStatus.REVIEW_REQUIRED,
        GateReasonCode.LOW_CONFIDENCE_OR_AMBIGUOUS_FINDING.value,
        False,
        ["c1"],
    ),
    # 6. No applicable checks -> REVIEW_REQUIRED (NO_APPLICABLE_CHECKS)
    (
        TranscriptIntegrityResult(is_valid=True),
        [],
        ScoreCalculationResult(overall_score=None, eligible_check_count=0, total_eligible_weight=0, is_scoreable=False),
        GateStatus.REVIEW_REQUIRED,
        GateReasonCode.NO_APPLICABLE_CHECKS.value,
        False,
        [],
    ),
    # 7. Applicable checks exist but not scoreable -> REVIEW_REQUIRED (NO_SCOREABLE_CHECKS)
    (
        TranscriptIntegrityResult(is_valid=True),
        [make_result("c1", False, CheckOutcome.NOT_EVALUABLE, confidence=None, score=None)],
        ScoreCalculationResult(overall_score=None, eligible_check_count=0, total_eligible_weight=0, is_scoreable=False),
        GateStatus.REVIEW_REQUIRED,
        GateReasonCode.NO_SCOREABLE_CHECKS.value,
        False,
        [],
    ),
    # 8. All critical pass, but overall score 75 (< 85) -> HELD (OVERALL_SCORE_BELOW_THRESHOLD)
    (
        TranscriptIntegrityResult(is_valid=True),
        [
            make_result("c1", True, CheckOutcome.PASS, confidence=0.95, score=100.0),
            make_result("c2", False, CheckOutcome.FAIL, confidence=0.95, score=50.0),
        ],
        ScoreCalculationResult(overall_score=75.0, eligible_check_count=2, total_eligible_weight=20, is_scoreable=True),
        GateStatus.HELD,
        GateReasonCode.OVERALL_SCORE_BELOW_THRESHOLD.value,
        False,
        [],
    ),
    # 9. All critical pass, score 90, but non-critical ambiguous -> REVIEW_REQUIRED (MANUAL_REVIEW_REQUESTED)
    (
        TranscriptIntegrityResult(is_valid=True),
        [
            make_result("c1", True, CheckOutcome.PASS, confidence=0.95, score=100.0),
            make_result("c2", False, CheckOutcome.AMBIGUOUS, confidence=0.75, score=80.0),
        ],
        ScoreCalculationResult(overall_score=90.0, eligible_check_count=2, total_eligible_weight=20, is_scoreable=True),
        GateStatus.REVIEW_REQUIRED,
        GateReasonCode.MANUAL_REVIEW_REQUESTED.value,
        False,
        ["c2"],
    ),
    # 10. All critical pass + non-critical fail + overall score 88 -> PASSED (ALL_CRITICAL_CHECKS_PASSED, auto_submitted=True)
    (
        TranscriptIntegrityResult(is_valid=True),
        [
            make_result("c1", True, CheckOutcome.PASS, confidence=0.95, score=100.0),
            make_result("c2", False, CheckOutcome.FAIL, confidence=0.95, score=76.0),
        ],
        ScoreCalculationResult(overall_score=88.0, eligible_check_count=2, total_eligible_weight=20, is_scoreable=True),
        GateStatus.PASSED,
        GateReasonCode.ALL_CRITICAL_CHECKS_PASSED.value,
        True,
        [],
    ),
]


@pytest.mark.parametrize(
    "tx_result,check_results,score_res,expected_status,expected_reason,expected_auto_submitted,expected_blocking",
    test_cases,
)
def test_deterministic_policy_precedence_truth_table(
    tx_result,
    check_results,
    score_res,
    expected_status,
    expected_reason,
    expected_auto_submitted,
    expected_blocking,
):
    resolved = [make_resolved_check(r.check_id, r.is_critical) for r in check_results]

    decision = DeterministicPolicyEngine.evaluate_gate(
        sale_id="sale-test",
        evaluation_run_id="eval-test",
        transcript_integrity=tx_result,
        check_results=check_results,
        resolved_checks=resolved,
        score_result=score_res,
    )

    assert decision.status == expected_status
    assert decision.decision_reason_code == expected_reason
    assert decision.auto_submitted == expected_auto_submitted
    assert decision.blocking_check_ids == expected_blocking
