"""Regression guard on scoring accuracy against the human-labelled calibration set.

This is the test that protects the number the brief judges hardest: a critical check must never
false-pass. It runs the real orchestrator over every labelled call, so any change to an evaluator,
threshold, or checklist parameter that would start disagreeing with human auditors fails here.
"""

import pytest

from packages.evaluation.accuracy import score_gold_set

# Raise these as the labelled set grows; they must never be lowered to make a change pass.
MIN_CHECK_AGREEMENT = 1.0
MIN_GATE_AGREEMENT = 1.0


@pytest.fixture(scope="module")
def report():
    return score_gold_set()


def test_every_labelled_case_scores_without_error(report):
    assert report.errored_cases == [], [
        (case.case_id, case.error) for case in report.errored_cases
    ]


def test_no_critical_check_false_passes(report):
    """The single most important guarantee in the system."""
    offenders = [
        (code, agreement.disagreements)
        for code, agreement in report.per_check.items()
        if agreement.is_critical and agreement.false_passes
    ]
    assert report.critical_false_passes == 0, offenders


def test_check_agreement_meets_threshold(report):
    assert report.check_agreement_rate >= MIN_CHECK_AGREEMENT, [
        (code, agreement.disagreements)
        for code, agreement in report.per_check.items()
        if agreement.disagreed
    ]


def test_gate_agreement_meets_threshold(report):
    assert report.gate_agreement_rate >= MIN_GATE_AGREEMENT, [
        (case.case_id, case.expected_gate, case.actual_gate)
        for case in report.cases
        if not case.gate_agreed
    ]


def test_applicability_rules_exclude_inapplicable_checks(report):
    """A gas sale must not be scored against the electricity meter check, and vice versa."""
    offenders = [
        (case.case_id, case.applicability_errors)
        for case in report.cases
        if case.applicability_errors
    ]
    assert offenders == []


def test_labelled_set_covers_all_three_check_tiers(report):
    """Coverage criterion: verbatim, factual and behaviour must all be exercised."""
    codes = set(report.per_check)
    assert any(code.startswith("VERBATIM_") for code in codes)
    assert any(code.startswith("FACTUAL_") for code in codes)
    assert any(code.startswith("BEHAVIOUR_") for code in codes)


def test_set_is_large_enough_to_be_meaningful(report):
    assert report.case_count >= 10
    assert report.labelled_check_total >= 40
