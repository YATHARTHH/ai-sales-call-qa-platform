"""Deterministic Policy Gate Engine enforcing the 11-condition precedence truth table."""

import hashlib
from collections.abc import Sequence

from packages.application.services.check_resolver import ResolvedCheck
from packages.application.services.transcript_validator import TranscriptIntegrityResult
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
    GateDecision,
    GateReasonCode,
)
from packages.domain.state import GateStatus
from packages.evaluation.policy.score_calculator import ScoreCalculationResult


class DeterministicPolicyEngine:
    """Evaluates check execution results against deterministic compliance policies.

    Principle: 'AI Proposes; Deterministic Policy Decides'.
    Adheres strictly to the 11-condition policy precedence truth table.
    """

    DEFAULT_PASSING_SCORE = 85.0
    CONFIDENCE_THRESHOLD = 0.80
    # Share of otherwise-clean calls diverted to a human so the model itself stays measured.
    DEFAULT_CLEAN_CALL_SAMPLE_RATE = 0.05

    @staticmethod
    def is_sampled_for_calibration(
        sale_id: str,
        policy_version: str,
        sample_rate: float,
    ) -> bool:
        """Deterministically decide whether a clean call is diverted to human QA.

        Selection is a pure function of the sale id and policy version, so a replayed evaluation
        of the same sale always reaches the same decision and reproducibility is preserved.
        """
        if sample_rate <= 0:
            return False
        if sample_rate >= 1:
            return True
        digest = hashlib.sha256(f"{policy_version}:{sale_id}".encode()).hexdigest()
        bucket = int(digest[:8], 16) % 10_000
        return bucket < int(round(sample_rate * 10_000))

    @classmethod
    def evaluate_gate(
        cls,
        sale_id: str,
        evaluation_run_id: str,
        transcript_integrity: TranscriptIntegrityResult,
        check_results: Sequence[CheckExecutionResult],
        resolved_checks: Sequence[ResolvedCheck],
        score_result: ScoreCalculationResult,
        policy_version: str = "policy.v1",
        passing_score_threshold: float = DEFAULT_PASSING_SCORE,
        clean_call_sample_rate: float = DEFAULT_CLEAN_CALL_SAMPLE_RATE,
    ) -> GateDecision:
        score = score_result.overall_score

        # 1. Condition 1: Incomplete or invalid transcript
        if not transcript_integrity.is_valid:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.HELD,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.TRANSCRIPT_INCOMPLETE.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=transcript_integrity.reason_codes or ["TRANSCRIPT_QUALITY_INVALID"],
                blocking_check_ids=[],
            )

        # Categorize critical checks
        critical_failed: list[str] = []
        critical_error: list[str] = []
        critical_unsupported: list[str] = []
        critical_low_confidence: list[str] = []

        for r in check_results:
            if not r.is_critical:
                continue

            if r.outcome == CheckOutcome.FAIL:
                critical_failed.append(r.check_id)
            elif r.outcome == CheckOutcome.NOT_EVALUABLE:
                critical_error.append(r.check_id)
            elif r.outcome == CheckOutcome.UNSUPPORTED:
                critical_unsupported.append(r.check_id)
            elif r.outcome == CheckOutcome.AMBIGUOUS:
                critical_low_confidence.append(r.check_id)
            elif r.confidence is not None and r.confidence < cls.CONFIDENCE_THRESHOLD:
                critical_low_confidence.append(r.check_id)

        # 2. Condition 2: Critical check failed
        if critical_failed:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.HELD,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.CRITICAL_CHECK_FAILED.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["ONE_OR_MORE_CRITICAL_CHECKS_FAILED"],
                blocking_check_ids=critical_failed,
            )

        # 3. Condition 3: Critical check execution error
        if critical_error:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.HELD,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.CRITICAL_CHECK_EXECUTION_ERROR.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["CRITICAL_CHECK_EXECUTION_ERROR"],
                blocking_check_ids=critical_error,
            )

        # 4. Condition 4: Unsupported critical check
        if critical_unsupported:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.HELD,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.UNSUPPORTED_CRITICAL_CHECK.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["UNSUPPORTED_CRITICAL_CHECK"],
                blocking_check_ids=critical_unsupported,
            )

        # 5. Condition 5: Low confidence or ambiguous finding on critical check
        if critical_low_confidence:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.REVIEW_REQUIRED,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.LOW_CONFIDENCE_OR_AMBIGUOUS_FINDING.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["LOW_CONFIDENCE_ON_CRITICAL_CHECK"],
                blocking_check_ids=critical_low_confidence,
            )

        # 6. Condition 6: No applicable checks resolved
        if len(resolved_checks) == 0:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.REVIEW_REQUIRED,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.NO_APPLICABLE_CHECKS.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["NO_APPLICABLE_CHECKS_RESOLVED"],
                blocking_check_ids=[],
            )

        # 7. Condition 7: No scoreable checks
        if not score_result.is_scoreable or score is None:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.REVIEW_REQUIRED,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.NO_SCOREABLE_CHECKS.value,
                overall_score=None,
                auto_submitted=False,
                reason_codes=["NO_SCOREABLE_CHECKS"],
                blocking_check_ids=[],
            )

        # 8. Condition 8: Overall score below threshold
        if score < passing_score_threshold:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.HELD,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.OVERALL_SCORE_BELOW_THRESHOLD.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=[f"OVERALL_SCORE_{score}_BELOW_{passing_score_threshold}"],
                blocking_check_ids=[],
            )

        # 9. Condition 9: Non-critical ambiguity or review request
        non_critical_ambiguous = [
            r.check_id for r in check_results if not r.is_critical and r.outcome == CheckOutcome.AMBIGUOUS
        ]
        if non_critical_ambiguous:
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.REVIEW_REQUIRED,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.MANUAL_REVIEW_REQUESTED.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["NON_CRITICAL_AMBIGUITY_REQUIRES_AUDIT"],
                blocking_check_ids=non_critical_ambiguous,
            )

        # 10. Condition 10: Otherwise-clean call selected for calibration sampling.
        # The sale is compliant; a human scores it anyway so agreement with the model can be
        # measured rather than assumed.
        if cls.is_sampled_for_calibration(sale_id, policy_version, clean_call_sample_rate):
            return GateDecision.create(
                sale_id=sale_id,
                evaluation_run_id=evaluation_run_id,
                status=GateStatus.REVIEW_REQUIRED,
                policy_version=policy_version,
                decision_reason_code=GateReasonCode.SAMPLED_FOR_CALIBRATION.value,
                overall_score=score,
                auto_submitted=False,
                reason_codes=["ALL_CRITICAL_CHECKS_PASSED", "SAMPLED_FOR_CALIBRATION"],
                blocking_check_ids=[],
                warnings=["Clean call diverted to human QA for model calibration."],
            )

        # 11. Condition 11: All critical checks passed & passing score achieved
        return GateDecision.create(
            sale_id=sale_id,
            evaluation_run_id=evaluation_run_id,
            status=GateStatus.PASSED,
            policy_version=policy_version,
            decision_reason_code=GateReasonCode.ALL_CRITICAL_CHECKS_PASSED.value,
            overall_score=score,
            auto_submitted=True,
            reason_codes=["ALL_CRITICAL_CHECKS_PASSED"],
            blocking_check_ids=[],
        )
