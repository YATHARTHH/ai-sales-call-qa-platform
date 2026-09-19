"""Score calculator with ScoreEligibility criteria and zero-denominator guard."""

from dataclasses import dataclass
from typing import Sequence

from packages.application.services.check_resolver import ResolvedCheck
from packages.domain.evaluation import CheckExecutionResult, CheckOutcome


@dataclass(frozen=True)
class ScoreCalculationResult:
    """Outcome of weighted check score computation."""

    overall_score: float | None
    eligible_check_count: int
    total_eligible_weight: int
    is_scoreable: bool


class EvaluationScoreCalculator:
    """Computes weighted QA score across applicable, score-eligible check results."""

    SCOREABLE_OUTCOMES = {
        CheckOutcome.PASS,
        CheckOutcome.FAIL,
        CheckOutcome.AMBIGUOUS,
    }

    @classmethod
    def calculate(
        cls,
        check_results: Sequence[CheckExecutionResult],
        resolved_checks_by_id: dict[str, ResolvedCheck],
    ) -> ScoreCalculationResult:
        weighted_sum = 0.0
        total_weight = 0
        eligible_count = 0

        for res in check_results:
            resolved = resolved_checks_by_id.get(res.check_id)
            weight = resolved.weight if resolved else 10

            # ScoreEligibility verification:
            # 1. Must have numeric score
            # 2. Must be in scoreable outcome set
            # 3. Weight must be positive
            if (
                res.score_numeric is not None
                and res.outcome in cls.SCOREABLE_OUTCOMES
                and weight > 0
            ):
                weighted_sum += res.score_numeric * weight
                total_weight += weight
                eligible_count += 1

        # Denominator guard: if no checks are eligible, score cannot be calculated
        if total_weight == 0 or eligible_count == 0:
            return ScoreCalculationResult(
                overall_score=None,
                eligible_check_count=0,
                total_eligible_weight=0,
                is_scoreable=False,
            )

        overall = round(weighted_sum / total_weight, 2)
        return ScoreCalculationResult(
            overall_score=overall,
            eligible_check_count=eligible_count,
            total_eligible_weight=total_weight,
            is_scoreable=True,
        )
