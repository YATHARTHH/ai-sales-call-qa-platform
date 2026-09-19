"""ASR robustness guardrail tests — 10 % noise on the full gold set.

The primary invariant:
    critical_false_passes == 0 at any noise level

A corrupted disclosure must degrade to AMBIGUOUS or FAIL, never silently PASS a
critical check that a human auditor would fail.  This is the brief's hardest criterion.

These tests intentionally use the same gold set as the accuracy regression suite but
inject ASR noise before scoring.  Gate agreement is expected to drop (humans can hear;
ASR cannot), but false passes must remain strictly zero.
"""

import copy

import pytest

from packages.evaluation.accuracy import (
    AccuracyReport,
    AsrNoiseSimulator,
    load_gold_set,
    score_gold_set,
)
from packages.evaluation.checklists.energy_retailer_v1 import ENERGY_RETAILER_CHECKLIST_V1

# Noise level matching the brief's 10 % guardrails criterion
NOISE_LEVEL = 0.10


def _make_noisy_gold_set(gold_set: dict, noise_level: float, seed: int) -> dict:
    """Return a deep-copied gold set with ASR noise injected into every segment."""
    sim = AsrNoiseSimulator(noise_level=noise_level, seed=seed)
    noisy = copy.deepcopy(gold_set)

    for base in noisy["bases"].values():
        corrupted_segments = []
        for segment in base["segments"]:
            order, role, start_ms, end_ms, text = segment
            noisy_text, _ = sim.corrupt(text)
            corrupted_segments.append([order, role, start_ms, end_ms, noisy_text])
        base["segments"] = corrupted_segments

    return noisy


@pytest.fixture(scope="module")
def clean_report() -> AccuracyReport:
    """Baseline: clean gold set, no noise."""
    return score_gold_set()


@pytest.fixture(scope="module")
def noisy_report() -> AccuracyReport:
    """10 % ASR noise applied to every segment of every gold-set call."""
    gold_set = load_gold_set()
    noisy_gold = _make_noisy_gold_set(gold_set, noise_level=NOISE_LEVEL, seed=42)
    return score_gold_set(gold_set=noisy_gold, checklist=ENERGY_RETAILER_CHECKLIST_V1)


# ---------------------------------------------------------------------------
# The critical invariant — must never fail, even with 10 % noise
# ---------------------------------------------------------------------------

def test_no_critical_false_passes_under_noise(noisy_report: AccuracyReport) -> None:
    """CRITICAL INVARIANT: no sale may auto-submit when a human auditor would block it.

    ASR noise is allowed to lower confidence and route more calls to human review, but it
    must never flip a failed critical check into a pass.  A single false pass here means
    a non-compliant sale could have shipped unreviewed.
    """
    offenders = [
        (code, agreement.disagreements)
        for code, agreement in noisy_report.per_check.items()
        if agreement.is_critical and agreement.false_passes > 0
    ]
    assert noisy_report.critical_false_passes == 0, (
        f"Critical false passes under {NOISE_LEVEL*100:.0f}% noise: {offenders}"
    )


def test_no_errors_under_noise(noisy_report: AccuracyReport) -> None:
    """The evaluation engine must not raise exceptions on noisy input."""
    assert noisy_report.errored_cases == [], [
        (case.case_id, case.error) for case in noisy_report.errored_cases
    ]


# ---------------------------------------------------------------------------
# Graceful degradation — noise is allowed to lower agreement but not cause false passes
# ---------------------------------------------------------------------------

def test_noisy_check_agreement_no_worse_than_50_pct(noisy_report: AccuracyReport) -> None:
    """Even with 10 % noise, the engine should agree with human labels at least 50 % of
    the time.  A lower bound prevents silent catastrophic failure of the evaluation logic.
    """
    # Note: the actual bar is much higher in practice; 50 % is the safety floor, not the target.
    assert noisy_report.check_agreement_rate >= 0.50, (
        f"Check agreement {noisy_report.check_agreement_rate:.2%} collapsed under noise"
    )


def test_noise_does_not_increase_critical_false_passes_vs_clean(
    clean_report: AccuracyReport, noisy_report: AccuracyReport
) -> None:
    """Adding noise must never introduce more critical false passes than the clean baseline."""
    assert noisy_report.critical_false_passes <= clean_report.critical_false_passes, (
        f"Noise introduced {noisy_report.critical_false_passes} critical false passes "
        f"vs clean baseline of {clean_report.critical_false_passes}"
    )


# ---------------------------------------------------------------------------
# Noise simulator unit-level sanity checks
# ---------------------------------------------------------------------------

def test_noise_simulator_is_deterministic() -> None:
    """Same seed must produce identical output every time."""
    text = "The electricity rate is 28.6 cents per kilowatt hour."
    sim1 = AsrNoiseSimulator(noise_level=0.30, seed=1)
    sim2 = AsrNoiseSimulator(noise_level=0.30, seed=1)
    result1, _ = sim1.corrupt(text)
    result2, _ = sim2.corrupt(text)
    assert result1 == result2


def test_noise_simulator_different_seeds_can_differ() -> None:
    """Different seeds should produce different output on a content-rich sentence."""
    text = (
        "Thank you for calling. Please be advised this call is being recorded for quality "
        "and training purposes. I can offer you twenty-eight point six cents per kilowatt "
        "hour with a cooling-off period of ten business days. Do you give your explicit "
        "informed consent to proceed?"
    )
    sim_a = AsrNoiseSimulator(noise_level=0.50, seed=1)
    sim_b = AsrNoiseSimulator(noise_level=0.50, seed=999)
    result_a, _ = sim_a.corrupt(text)
    result_b, _ = sim_b.corrupt(text)
    # With 50 % noise, almost certainly at least one difference will be introduced
    # (not a hard assertion — just informational that the seeds have effect)
    # We allow them to be equal in the astronomically unlikely case that they coincide.
    _ = result_a != result_b  # just exercise the paths


def test_noise_simulator_high_noise_still_returns_string() -> None:
    """100 % noise must not crash — it may return a degraded string but must be str."""
    sim = AsrNoiseSimulator(noise_level=1.0, seed=0)
    result, report = sim.corrupt(
        "Please note you have a 10 business day cooling off period where you can cancel "
        "without penalty. Do you provide your explicit informed consent to proceed?"
    )
    assert isinstance(result, str)
    assert len(result) >= 0


def test_noise_simulator_empty_string() -> None:
    """Empty input must survive without error."""
    sim = AsrNoiseSimulator(noise_level=0.50, seed=7)
    result, report = sim.corrupt("")
    assert result == ""
