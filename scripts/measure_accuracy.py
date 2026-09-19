"""Score the evaluation engine against the human-labelled calibration set.

    python scripts/measure_accuracy.py
    python scripts/measure_accuracy.py --json reports/accuracy.json
    python scripts/measure_accuracy.py --fail-under 0.95

Exits non-zero when a critical check false-passed, when a case errored, or when agreement falls
below --fail-under, so this can gate CI as well as inform a demo.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from packages.evaluation.accuracy.harness import (  # noqa: E402
    AccuracyReport,
    load_gold_set,
    report_to_dict,
    score_gold_set,
)

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _colour(enabled: bool, code: str) -> str:
    return code if enabled else ""


def print_report(report: AccuracyReport, colour: bool = True) -> None:
    c = lambda code: _colour(colour, code)  # noqa: E731

    print()
    print(f"{c(BOLD)}Scoring accuracy vs human auditors{c(RESET)}")
    print(f"{c(DIM)}dataset {report.dataset_version}{c(RESET)}")
    print("=" * 72)

    false_pass_colour = c(GREEN) if report.critical_false_passes == 0 else c(RED)
    print(
        f"  Critical false-passes   {false_pass_colour}{report.critical_false_passes}{c(RESET)}"
        f"   {c(DIM)}(a critical check the engine passed and a human failed){c(RESET)}"
    )
    print(f"  Critical false-fails    {report.critical_false_fails}")
    print(
        f"  Check agreement         {report.check_agreement_rate:.1%}"
        f"   {c(DIM)}({report.checks_agreed}/{report.labelled_check_total} labelled checks){c(RESET)}"
    )
    print(f"  Gate agreement          {report.gate_agreement_rate:.1%}")
    print(f"  Cases                   {report.case_count}")
    if report.errored_cases:
        print(f"  {c(RED)}Errored cases           {len(report.errored_cases)}{c(RESET)}")
    print()

    disagreeing = {
        code: agreement
        for code, agreement in report.per_check.items()
        if agreement.disagreed
    }
    if disagreeing:
        print(f"{c(BOLD)}Checks that disagreed{c(RESET)}")
        print("-" * 72)
        for code, agreement in sorted(disagreeing.items()):
            marker = "critical" if agreement.is_critical else "non-critical"
            print(f"  {code}  ({marker})  {agreement.agreement_rate:.0%}")
            for detail in agreement.disagreements:
                print(f"      {c(YELLOW)}{detail}{c(RESET)}")
        print()

    problem_cases = [
        case
        for case in report.cases
        if case.error or not case.gate_agreed or case.applicability_errors
    ]
    if problem_cases:
        print(f"{c(BOLD)}Cases needing attention{c(RESET)}")
        print("-" * 72)
        for case in problem_cases:
            print(f"  {c(RED)}{case.case_id}{c(RESET)}  {case.description}")
            if case.error:
                print(f"      error: {case.error}")
            if not case.gate_agreed:
                print(f"      gate: expected {case.expected_gate}, got {case.actual_gate}")
            for code in case.applicability_errors:
                print(f"      {code} ran but should not have been applicable")
        print()
    else:
        print(f"{c(GREEN)}All cases reached the gate decision the auditor recorded.{c(RESET)}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-set", type=Path, default=None, help="Path to the labelled set")
    parser.add_argument("--json", type=Path, default=None, help="Write the full report as JSON")
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit non-zero if check agreement falls below this rate (e.g. 0.95)",
    )
    parser.add_argument("--no-colour", action="store_true")
    args = parser.parse_args()

    gold_set = load_gold_set(args.gold_set) if args.gold_set else load_gold_set()
    report = score_gold_set(gold_set)

    print_report(report, colour=not args.no_colour)

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report_to_dict(report), indent=2), encoding="utf-8"
        )
        print(f"Report written to {args.json}")

    if report.critical_false_passes:
        print("FAILED: a critical check false-passed.")
        return 1
    if report.errored_cases:
        print("FAILED: one or more cases could not be scored.")
        return 1
    if args.fail_under is not None and report.check_agreement_rate < args.fail_under:
        print(
            f"FAILED: check agreement {report.check_agreement_rate:.1%} "
            f"is below the required {args.fail_under:.1%}."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
