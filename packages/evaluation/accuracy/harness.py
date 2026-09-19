"""Scores the evaluation engine against a human-labelled calibration set.

The headline number is not overall agreement, it is **critical false-pass count**: how often the
engine passed a critical check a human auditor failed. That is the failure mode a retailer audit
punishes, and it must be zero.

Calibration sampling is disabled while scoring so gate expectations stay deterministic; sampling
is a routing policy, not a scoring behaviour.
"""

import copy
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.domain.evaluation import CheckOutcome
from packages.domain.provenance import AIProvenance
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)
from packages.evaluation.checklists.builder import build_check_library
from packages.evaluation.checklists.energy_retailer_v1 import (
    ENERGY_RETAILER_CHECKLIST_V1,
    ChecklistEntry,
)
from packages.evaluation.engine import EvaluationOrchestrator

DEFAULT_GOLD_SET = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "gold" / "energy_gold_set_v1.json"
)

# Verdicts that mean "this check did not clear on its own"; used to classify false passes.
_NON_PASSING = {
    CheckOutcome.FAIL.value,
    CheckOutcome.AMBIGUOUS.value,
    CheckOutcome.NOT_EVALUABLE.value,
    CheckOutcome.UNSUPPORTED.value,
}


@dataclass
class CheckAgreement:
    """Per-check-code agreement tally across the whole set."""

    check_code: str
    is_critical: bool
    agreed: int = 0
    disagreed: int = 0
    false_passes: int = 0
    false_fails: int = 0
    disagreements: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.agreed + self.disagreed

    @property
    def agreement_rate(self) -> float:
        return self.agreed / self.total if self.total else 1.0


@dataclass
class CaseOutcome:
    """Result of scoring one labelled call."""

    case_id: str
    description: str
    expected_gate: str | None
    actual_gate: str
    gate_agreed: bool
    checks_agreed: int
    checks_disagreed: int
    disagreements: list[dict[str, str]] = field(default_factory=list)
    applicability_errors: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class AccuracyReport:
    """Aggregate accuracy of the engine against the labelled set."""

    dataset_version: str
    case_count: int
    cases: list[CaseOutcome]
    per_check: dict[str, CheckAgreement]

    @property
    def labelled_check_total(self) -> int:
        return sum(agreement.total for agreement in self.per_check.values())

    @property
    def checks_agreed(self) -> int:
        return sum(agreement.agreed for agreement in self.per_check.values())

    @property
    def check_agreement_rate(self) -> float:
        return self.checks_agreed / self.labelled_check_total if self.labelled_check_total else 1.0

    @property
    def gate_agreement_rate(self) -> float:
        scored = [case for case in self.cases if case.expected_gate]
        return sum(case.gate_agreed for case in scored) / len(scored) if scored else 1.0

    @property
    def critical_false_passes(self) -> int:
        """Critical checks the engine passed that a human auditor did not. Must be zero."""
        return sum(a.false_passes for a in self.per_check.values() if a.is_critical)

    @property
    def critical_false_fails(self) -> int:
        return sum(a.false_fails for a in self.per_check.values() if a.is_critical)

    @property
    def errored_cases(self) -> list[CaseOutcome]:
        return [case for case in self.cases if case.error]


# ======================================================================================
# Gold set loading and case materialisation
# ======================================================================================


def load_gold_set(path: Path | str = DEFAULT_GOLD_SET) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge patch into a copy of base. An explicit null removes the key."""
    merged = copy.deepcopy(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def materialise_case(gold_set: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    """Apply a case's overrides to its base call and return the concrete scenario."""
    base = gold_set["bases"][case["base"]]

    sale = _deep_merge(base["sale"], case.get("sale_patch", {}))
    lead = _deep_merge(base["lead"], case.get("lead_patch", {}))

    removals = set(case.get("segment_removals", []))
    overrides = {int(k): v for k, v in case.get("segment_overrides", {}).items()}
    shifts = {int(k): int(v) for k, v in case.get("segment_time_shifts", {}).items()}

    segments: list[list[Any]] = []
    for order, role, start_ms, end_ms, text in base["segments"]:
        if order in removals:
            continue
        shift = shifts.get(order, 0)
        segments.append(
            [order, role, start_ms + shift, end_ms + shift, overrides.get(order, text)]
        )

    return {
        "call_date": base["call_date"],
        "sale": sale,
        "lead": lead,
        "segments": segments,
    }


def _build_transcript(
    scenario: dict[str, Any], case_id: str
) -> tuple[Transcript, list[TranscriptSegment], Recording]:
    call_date = datetime.fromisoformat(scenario["call_date"])
    raw_segments = scenario["segments"]
    duration_ms = max(segment[3] for segment in raw_segments)

    recording = Recording.create(
        sale_id=f"sale-{case_id}",
        artifact_id=f"art-{case_id}",
        dialler_call_id=f"call-{case_id}",
        duration_seconds=duration_ms / 1000,
        call_date=call_date,
        recording_id=f"rec-{case_id}",
    )

    transcript = Transcript(
        id=f"tx-{case_id}",
        recording_id=recording.id,
        source_artifact_id=recording.artifact_id,
        output_artifact_id=f"art-tx-{case_id}",
        asr_provider="gold-set",
        asr_model="labelled-fixture",
        asr_model_version="1.0",
        diarization_provider="stereo-channel",
        diarization_version="stereo-channel-v1",
        availability=TranscriptAvailability.AVAILABLE,
        audio_duration_ms=duration_ms,
        created_at=call_date,
    )

    segments = [
        TranscriptSegment.create(
            transcript_id=transcript.id,
            segment_order=index,
            business_role=SpeakerType.AGENT if role == "AGENT" else SpeakerType.CUSTOMER,
            start_ms=start_ms,
            end_ms=end_ms,
            text=text,
            segment_id=f"{case_id}-seg-{order}",
        )
        for index, (order, role, start_ms, end_ms, text) in enumerate(raw_segments, start=1)
    ]

    return transcript, segments, recording


# ======================================================================================
# Scoring
# ======================================================================================


def score_gold_set(
    gold_set: dict[str, Any] | None = None,
    checklist: Sequence[ChecklistEntry] = ENERGY_RETAILER_CHECKLIST_V1,
) -> AccuracyReport:
    """Run the real evaluation engine over every labelled case and tally agreement."""
    gold_set = gold_set or load_gold_set()
    entries_by_code = {entry.check_code: entry for entry in checklist}
    definitions, versions_by_id = build_check_library(
        entries=checklist, retailer_id=gold_set["retailer_id"]
    )
    code_by_check_id = {entry.check_id: entry.check_code for entry in checklist}

    orchestrator = EvaluationOrchestrator()
    provenance = AIProvenance(
        provider="deterministic-evaluator",
        model="qa-gate-engine",
        model_version="1.0.0",
        prompt_version="rules.v1",
        check_version="check_set.v1",
        policy_version="policy.v1",
    )

    per_check: dict[str, CheckAgreement] = {}
    cases: list[CaseOutcome] = []

    for case in gold_set["cases"]:
        case_id = case["case_id"]
        try:
            scenario = materialise_case(gold_set, case)
            transcript, segments, recording = _build_transcript(scenario, case_id)

            payload = orchestrator.execute_evaluation(
                sale_id=f"sale-{case_id}",
                tenant_id=gold_set["retailer_id"],
                transcript=transcript,
                segments=segments,
                recording=recording,
                check_definitions=definitions,
                check_versions_by_id=versions_by_id,
                sale_data=scenario["sale"],
                lead_data=scenario["lead"],
                provenance=provenance,
                # Sampling is a routing policy; it must not perturb accuracy measurement.
                clean_call_sample_rate=0.0,
            )
        except Exception as exc:  # A broken case must be reported, never silently skipped.
            cases.append(
                CaseOutcome(
                    case_id=case_id,
                    description=case.get("description", ""),
                    expected_gate=case.get("expected_gate"),
                    actual_gate="ERROR",
                    gate_agreed=False,
                    checks_agreed=0,
                    checks_disagreed=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        actual_by_code = {
            code_by_check_id[result.check_id]: result.result.value
            for result in payload.results
            if result.check_id in code_by_check_id
        }
        evaluated_codes = set(actual_by_code)

        agreed = 0
        disagreed = 0
        disagreements: list[dict[str, str]] = []

        for check_code, expected in case.get("expected_checks", {}).items():
            entry = entries_by_code.get(check_code)
            if entry is None:
                continue
            agreement = per_check.setdefault(
                check_code, CheckAgreement(check_code, entry.is_critical)
            )

            actual = actual_by_code.get(check_code, "NOT_EVALUATED")
            if actual == expected:
                agreement.agreed += 1
                agreed += 1
                continue

            agreement.disagreed += 1
            disagreed += 1
            if actual == CheckOutcome.PASS.value and expected in _NON_PASSING:
                agreement.false_passes += 1
            elif expected == CheckOutcome.PASS.value and actual in _NON_PASSING:
                agreement.false_fails += 1
            agreement.disagreements.append(f"{case_id}: expected {expected}, got {actual}")
            disagreements.append(
                {"check_code": check_code, "expected": expected, "actual": actual}
            )

        applicability_errors = [
            code
            for code in case.get("expected_not_applicable", [])
            if code in evaluated_codes
        ]

        expected_gate = case.get("expected_gate")
        actual_gate = payload.gate_decision.status.value
        cases.append(
            CaseOutcome(
                case_id=case_id,
                description=case.get("description", ""),
                expected_gate=expected_gate,
                actual_gate=actual_gate,
                gate_agreed=expected_gate is None or expected_gate == actual_gate,
                checks_agreed=agreed,
                checks_disagreed=disagreed,
                disagreements=disagreements,
                applicability_errors=applicability_errors,
            )
        )

    return AccuracyReport(
        dataset_version=gold_set["dataset_version"],
        case_count=len(gold_set["cases"]),
        cases=cases,
        per_check=per_check,
    )


def report_to_dict(report: AccuracyReport) -> dict[str, Any]:
    """Serialise a report for storage or CI comparison."""
    return {
        "dataset_version": report.dataset_version,
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "case_count": report.case_count,
            "labelled_checks": report.labelled_check_total,
            "check_agreement_rate": round(report.check_agreement_rate, 4),
            "gate_agreement_rate": round(report.gate_agreement_rate, 4),
            "critical_false_passes": report.critical_false_passes,
            "critical_false_fails": report.critical_false_fails,
            "errored_cases": len(report.errored_cases),
        },
        "per_check": {
            code: {
                "is_critical": agreement.is_critical,
                "agreed": agreement.agreed,
                "disagreed": agreement.disagreed,
                "agreement_rate": round(agreement.agreement_rate, 4),
                "false_passes": agreement.false_passes,
                "false_fails": agreement.false_fails,
                "disagreements": agreement.disagreements,
            }
            for code, agreement in sorted(report.per_check.items())
        },
        "cases": [
            {
                "case_id": case.case_id,
                "description": case.description,
                "expected_gate": case.expected_gate,
                "actual_gate": case.actual_gate,
                "gate_agreed": case.gate_agreed,
                "checks_agreed": case.checks_agreed,
                "checks_disagreed": case.checks_disagreed,
                "disagreements": case.disagreements,
                "applicability_errors": case.applicability_errors,
                "error": case.error,
            }
            for case in report.cases
        ],
    }
