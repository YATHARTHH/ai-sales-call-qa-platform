"""The adjudication contract shared by every provider.

One prompt, one payload shape, one response validator. Keeping these in a single place is what
makes providers genuinely interchangeable: a Claude verdict and a Gemini verdict are produced from
identical instructions and validated by identical rules, so their agreement on the calibration set
is a measurement of the models rather than of two different prompts.
"""

from typing import Any

from packages.application.ports.adjudicator import (
    AdjudicationRequest,
    AdjudicationVerdict,
    AdjudicationVerdictType,
)
from packages.observability.logging import get_logger

logger = get_logger("adjudication.contract")

ADJUDICATION_PROMPT_VERSION = "adjudicator.v1"

ADJUDICATION_SYSTEM_PROMPT = """You are a compliance auditor for Australian energy and \
telecommunications sales calls. A deterministic rule engine has already scored this call and could \
not settle one check. Your job is to say whether the transcript satisfies that one requirement.

Rules you must follow:
- Decide only from the transcript lines provided. Never assume something was said because it \
usually is.
- A requirement is SATISFIED only if a provided line actually conveys it. Wording may differ from \
the script; meaning may not.
- If the lines are garbled, ambiguous, or simply do not cover the requirement, answer \
CANNOT_DETERMINE. That is a correct and useful answer, and it sends the call to a human.
- Never answer SATISFIED to be helpful. A wrong SATISFIED lets a non-compliant sale ship.
- Cite the segment_id of the single line your answer rests on. Use null if none applies.
- confidence is your probability that your own verdict is correct, from 0.0 to 1.0."""


def build_adjudication_payload(request: AdjudicationRequest) -> dict[str, Any]:
    """Serialise one unresolved check into the payload every provider receives."""
    return {
        "check_code": request.check_code,
        "check_name": request.check_name,
        "requirement": request.requirement,
        "expected_value": request.expected_value,
        "value_heard_by_rule_engine": request.observed_value,
        "rule_engine_outcome": request.engine_outcome,
        "rule_engine_confidence": request.engine_confidence,
        "rule_engine_reason_codes": request.engine_reason_codes,
        "candidate_transcript_lines": [
            {
                "segment_id": segment.segment_id,
                "speaker": segment.speaker,
                "start_ms": segment.start_ms,
                "end_ms": segment.end_ms,
                "text": segment.text,
            }
            for segment in request.segments
        ],
    }


def build_verdict(
    parsed: dict[str, Any],
    request: AdjudicationRequest,
    provider: str,
    model: str,
    model_version: str | None = None,
) -> AdjudicationVerdict:
    """Validate a raw provider response into a verdict, or decline it.

    Shared by every provider so the same validation — a known verdict value, a citation that
    actually exists — protects the policy layer regardless of which model answered.
    """
    raw_verdict = str(parsed.get("verdict", "")).strip().upper()
    try:
        verdict = AdjudicationVerdictType(raw_verdict)
    except ValueError:
        logger.warning("adjudication_unknown_verdict", verdict=raw_verdict)
        return AdjudicationVerdict.undetermined(
            f"Adjudicator returned an unrecognised verdict: {raw_verdict!r}"
        )

    supporting = parsed.get("supporting_segment_id") or None
    valid_segment_ids = {segment.segment_id for segment in request.segments}
    if supporting is not None and supporting not in valid_segment_ids:
        # A citation that does not exist cannot ground evidence, so the verdict is not usable.
        logger.warning(
            "adjudication_invalid_citation", check_code=request.check_code, cited=supporting
        )
        return AdjudicationVerdict.undetermined(
            "Adjudicator cited a transcript line that was not supplied."
        )

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    return AdjudicationVerdict(
        verdict=verdict,
        confidence=max(0.0, min(1.0, confidence)),
        rationale=str(parsed.get("rationale", "")).strip(),
        supporting_segment_id=supporting,
        provider=provider,
        model=model,
        model_version=model_version or model,
        prompt_version=ADJUDICATION_PROMPT_VERSION,
    )
