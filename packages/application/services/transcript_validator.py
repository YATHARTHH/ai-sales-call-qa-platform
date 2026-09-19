"""Validator for transcript quality, completeness, and lineage prior to evaluation."""

from dataclasses import dataclass, field
from typing import Sequence

from packages.domain.speech_metrics import Interval, union_intervals
from packages.domain.transcript import (
    Recording,
    SpeakerType,
    Transcript,
    TranscriptAvailability,
    TranscriptSegment,
)


@dataclass(frozen=True)
class TranscriptIntegrityResult:
    """Outcome of pre-evaluation transcript quality and lineage verification."""

    is_valid: bool
    reason_codes: list[str] = field(default_factory=list)
    agent_duration_ratio: float = 0.0
    customer_duration_ratio: float = 0.0
    unknown_duration_ratio: float = 0.0
    total_duration_ms: int = 0
    segment_count: int = 0

    @property
    def has_active_conversation(self) -> bool:
        return self.agent_duration_ratio > 0.0 and self.customer_duration_ratio > 0.0


class TranscriptIntegrityValidator:
    """Deterministic validator enforcing all pre-evaluation transcript invariants."""

    @classmethod
    def validate(
        cls,
        transcript: Transcript,
        segments: Sequence[TranscriptSegment],
        recording: Recording | None = None,
        expected_audio_artifact_hash: str | None = None,
    ) -> TranscriptIntegrityResult:
        reason_codes: list[str] = []

        # 1. Determine authoritative audio duration
        duration_ms = 0
        if recording is not None and recording.validated_audio_duration_ms > 0:
            duration_ms = recording.validated_audio_duration_ms
        elif transcript.audio_duration_ms > 0:
            duration_ms = transcript.audio_duration_ms

        if duration_ms <= 0:
            reason_codes.append("INVALID_AUDIO_DURATION")

        # 2. Lineage verification
        if recording is not None:
            if transcript.source_artifact_id != recording.artifact_id:
                reason_codes.append("LINEAGE_ARTIFACT_MISMATCH")

        # 3. Availability check
        if transcript.availability != TranscriptAvailability.AVAILABLE:
            reason_codes.append("TRANSCRIPT_NOT_AVAILABLE")

        # 4. Segment count check
        if not segments or len(segments) == 0:
            reason_codes.append("EMPTY_TRANSCRIPT_SEGMENTS")
            return TranscriptIntegrityResult(
                is_valid=False,
                reason_codes=reason_codes,
                total_duration_ms=duration_ms,
                segment_count=0,
            )

        # 5. Segment ordering & timestamp validity
        prev_order = 0
        agent_intervals: list[Interval] = []
        customer_intervals: list[Interval] = []
        unknown_intervals: list[Interval] = []
        same_speaker_last_end: dict[str, int] = {}

        valid_roles = {SpeakerType.AGENT, SpeakerType.CUSTOMER, SpeakerType.UNKNOWN}

        for seg in segments:
            # Segment order must be unique and strictly increasing 1, 2, 3...
            if seg.segment_order != prev_order + 1:
                reason_codes.append(f"INVALID_SEGMENT_ORDER_{seg.segment_order}")
            prev_order = seg.segment_order

            # Timestamps: 0 <= start_ms < end_ms <= duration_ms
            if seg.start_ms < 0:
                reason_codes.append(f"NEGATIVE_START_TIME_{seg.segment_order}")
            if seg.end_ms <= seg.start_ms:
                reason_codes.append(f"INVERTED_TIMESTAMPS_{seg.segment_order}")
            if duration_ms > 0 and seg.end_ms > duration_ms:
                reason_codes.append(f"TIMESTAMP_EXCEEDS_DURATION_{seg.segment_order}")

            # Business role check
            if seg.business_role not in valid_roles:
                reason_codes.append(f"INVALID_BUSINESS_ROLE_{seg.segment_order}")

            # Same-speaker overlap check (excessive overlap > 1000ms is anomalous)
            spk_key = seg.speaker_label or seg.business_role.value
            last_end = same_speaker_last_end.get(spk_key, 0)
            if seg.start_ms < last_end:
                overlap = last_end - seg.start_ms
                if overlap > 1000:
                    reason_codes.append(f"EXCESSIVE_SAME_SPEAKER_OVERLAP_{seg.segment_order}")
            same_speaker_last_end[spk_key] = max(last_end, seg.end_ms)

            # Categorize valid intervals for talk time
            if seg.end_ms > seg.start_ms and seg.start_ms >= 0:
                iv = Interval(start_ms=seg.start_ms, end_ms=seg.end_ms)
                if seg.business_role == SpeakerType.AGENT:
                    agent_intervals.append(iv)
                elif seg.business_role == SpeakerType.CUSTOMER:
                    customer_intervals.append(iv)
                else:
                    unknown_intervals.append(iv)

        # 6. Compute speech duration metrics
        agent_active_ms = sum(iv.duration_ms for iv in union_intervals(agent_intervals))
        customer_active_ms = sum(iv.duration_ms for iv in union_intervals(customer_intervals))
        unknown_active_ms = sum(iv.duration_ms for iv in union_intervals(unknown_intervals))

        effective_duration = max(duration_ms, 1)
        agent_ratio = round(agent_active_ms / effective_duration, 4)
        customer_ratio = round(customer_active_ms / effective_duration, 4)
        unknown_ratio = round(unknown_active_ms / effective_duration, 4)

        if customer_active_ms == 0:
            reason_codes.append("NO_CUSTOMER_SPEECH_DETECTED")
        if agent_active_ms == 0:
            reason_codes.append("NO_AGENT_SPEECH_DETECTED")

        is_valid = len(reason_codes) == 0

        return TranscriptIntegrityResult(
            is_valid=is_valid,
            reason_codes=reason_codes,
            agent_duration_ratio=agent_ratio,
            customer_duration_ratio=customer_ratio,
            unknown_duration_ratio=unknown_ratio,
            total_duration_ms=duration_ms,
            segment_count=len(segments),
        )
