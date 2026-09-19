"""Evaluator registry and dispatcher for multi-tier QA evaluation."""

import logging
from collections.abc import Sequence

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import (
    CheckExecutionResult,
    CheckOutcome,
)
from packages.evaluation.base import BaseCheckEvaluator, EvaluatorContext

logger = logging.getLogger(__name__)


class EvaluatorRegistry:
    """Maintains registered evaluators and securely dispatches check executions."""

    def __init__(self, evaluators: Sequence[BaseCheckEvaluator] | None = None):
        self._evaluators: list[BaseCheckEvaluator] = list(evaluators or [])

    def register(self, evaluator: BaseCheckEvaluator) -> None:
        self._evaluators.append(evaluator)

    def find_evaluator(self, check: ResolvedCheck) -> BaseCheckEvaluator | None:
        for evaluator in self._evaluators:
            if evaluator.can_evaluate(check):
                return evaluator
        return None

    def evaluate_check(
        self,
        check: ResolvedCheck,
        context: EvaluatorContext,
    ) -> CheckExecutionResult:
        evaluator = self.find_evaluator(check)
        if evaluator is None:
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=CheckOutcome.UNSUPPORTED,
                confidence=None,
                score_numeric=None,
                evidences=[],
                reason_codes=["UNSUPPORTED_CHECK_TYPE"],
            )

        try:
            return evaluator.evaluate(check, context)
        except Exception:
            logger.exception("Evaluator raised exception for check %s", check.check_code)
            return CheckExecutionResult(
                check_id=check.check_id,
                check_version_id=check.version_id,
                is_critical=check.is_critical,
                outcome=CheckOutcome.NOT_EVALUABLE,
                confidence=None,
                score_numeric=None,
                evidences=[],
                reason_codes=["EVALUATOR_EXECUTION_ERROR"],
            )
