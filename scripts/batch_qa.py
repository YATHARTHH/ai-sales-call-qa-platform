"""Batch Sales Call QA CLI — Process bulk transcripts or audio files and generate compliance summaries.

Usage:
    python scripts/batch_qa.py --domain energy --output-json scratch/batch_results.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from packages.evaluation.accuracy.harness import load_gold_set, score_gold_set
from packages.evaluation.checklists.energy_retailer_v1 import ENERGY_RETAILER_CHECKLIST_V1
from packages.evaluation.checklists.broadband_retailer_v1 import BROADBAND_RETAILER_CHECKLIST_V1


def main():
    parser = argparse.ArgumentParser(description="Batch QA Processing CLI for Sales Calls")
    parser.add_argument("--domain", choices=["energy", "broadband"], default="energy", help="Domain checklist to evaluate against")
    parser.add_argument("--output-json", type=str, default="", help="Path to save JSON summary report")

    args = parser.parse_args()

    checklist = BROADBAND_RETAILER_CHECKLIST_V1 if args.domain == "broadband" else ENERGY_RETAILER_CHECKLIST_V1
    print(f"Loaded {len(checklist)} checks for domain '{args.domain}'")

    gold_set = load_gold_set()
    num_cases = len(gold_set.get("cases", {}))

    print(f"Starting batch QA evaluation on {num_cases} test cases...")
    start_total = time.perf_counter()

    report = score_gold_set(gold_set=gold_set, checklist=checklist)

    total_time = time.perf_counter() - start_total
    throughput = num_cases / total_time if total_time > 0 else 0

    print("\n" + "=" * 60)
    print("BATCH PROCESSING COMPLETED SUMMARY")
    print("=" * 60)
    print(f"Total Calls Evaluated: {report.case_count}")
    print(f"Check Agreement Rate: {report.check_agreement_rate:.2%}")
    print(f"Critical False Passes: {report.critical_false_passes}")
    print(f"Errored Cases:        {len(report.errored_cases)}")
    print(f"Total Processing Time:{total_time:.3f} seconds")
    print(f"Throughput:           {throughput:.2f} calls/sec")
    print("=" * 60)

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "summary": {
                    "domain": args.domain,
                    "total_cases": report.case_count,
                    "check_agreement_rate": round(report.check_agreement_rate, 4),
                    "critical_false_passes": report.critical_false_passes,
                    "errored_cases_count": len(report.errored_cases),
                    "throughput_calls_per_sec": round(throughput, 2),
                    "total_time_sec": round(total_time, 3)
                },
                "per_check_agreement": {
                    k: {
                        "agreement_rate": round(v.agreement_rate, 4),
                        "false_passes": v.false_passes,
                        "false_fails": v.false_fails,
                        "is_critical": v.is_critical
                    }
                    for k, v in report.per_check.items()
                }
            }, f, indent=2)
        print(f"Saved JSON report to {args.output_json}")


if __name__ == "__main__":
    main()
