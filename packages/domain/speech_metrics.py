"""Pure domain logic for speech behavior metrics, talk time calculation, and dead-air detection.

Zero external dependencies allowed (pure Python).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Interval:
    """Time interval in milliseconds."""

    start_ms: int
    end_ms: int

    def __post_init__(self):
        if self.end_ms < self.start_ms:
            raise ValueError(f"Interval end_ms ({self.end_ms}) cannot be before start_ms ({self.start_ms})")

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def union_intervals(intervals: Sequence[Interval]) -> list[Interval]:
    """Merge overlapping and adjacent intervals to prevent double-counting talk time.

    Returns a list of disjoint, sorted intervals.
    """
    if not intervals:
        return []

    sorted_intervals = sorted(intervals, key=lambda iv: (iv.start_ms, iv.end_ms))
    merged: list[Interval] = [sorted_intervals[0]]

    for current in sorted_intervals[1:]:
        last = merged[-1]
        if current.start_ms <= last.end_ms:
            # Overlap or boundary touch: extend interval
            merged[-1] = Interval(start_ms=last.start_ms, end_ms=max(last.end_ms, current.end_ms))
        else:
            merged.append(current)

    return merged


def total_duration_ms(intervals: Sequence[Interval]) -> int:
    """Calculate total non-overlapping duration for a sequence of intervals."""
    return sum(iv.duration_ms for iv in union_intervals(intervals))


@dataclass(frozen=True)
class SilenceInterval:
    """Internal dead air silence interval between conversational speech utterances."""

    start_ms: int
    end_ms: int
    duration_ms: int


@dataclass(frozen=True)
class InterruptionCandidate:
    """Candidate conversational interruption where a second speaker overlaps the active speaker."""

    speaker_label: str
    interrupted_speaker_label: str
    start_ms: int
    overlap_duration_ms: int


@dataclass(frozen=True)
class SpeechBehaviorMetrics:
    """Objective speech behavior observations for a sales call."""

    audio_duration_ms: int
    transcribed_coverage_end_ms: int
    leading_uncovered_ms: int
    trailing_uncovered_ms: int
    has_uncovered_audio: bool
    agent_talk_ms: int
    customer_talk_ms: int
    total_speech_ms: int
    agent_talk_percentage: float
    customer_talk_percentage: float
    conversational_occupancy_percentage: float
    agent_words_per_minute: float
    customer_words_per_minute: float
    dead_air_gaps: list[SilenceInterval] = field(default_factory=list)
    interruption_candidates: list[InterruptionCandidate] = field(default_factory=list)


@dataclass
class SpeechBehaviorAnalyzer:
    """Analyzes speech segments against authoritative audio duration to yield objective metrics."""

    dead_air_threshold_ms: int = 45_000
    interruption_min_duration_ms: int = 500
    coverage_tolerance_ms: int = 5_000

    def analyze(
        self,
        utterances: Sequence[object],
        audio_duration_ms: int,
        role_mapping: dict[str, str] | None = None,
    ) -> SpeechBehaviorMetrics:
        """Calculate speech metrics from utterances and authoritative audio duration.

        `utterances` may be raw domain Utterance, TranscriptSegment, or RawUtterance objects
        having attributes `start_ms`, `end_ms`, `speaker_label` (or `speaker`), and `text`.
        """
        role_map = role_mapping or {}

        if not utterances:
            return SpeechBehaviorMetrics(
                audio_duration_ms=audio_duration_ms,
                transcribed_coverage_end_ms=0,
                leading_uncovered_ms=audio_duration_ms,
                trailing_uncovered_ms=audio_duration_ms,
                has_uncovered_audio=audio_duration_ms > self.coverage_tolerance_ms,
                agent_talk_ms=0,
                customer_talk_ms=0,
                total_speech_ms=0,
                agent_talk_percentage=0.0,
                customer_talk_percentage=0.0,
                conversational_occupancy_percentage=0.0,
                agent_words_per_minute=0.0,
                customer_words_per_minute=0.0,
                dead_air_gaps=[],
                interruption_candidates=[],
            )

        # Sort utterances deterministically
        sorted_utts = sorted(
            utterances,
            key=lambda u: (
                getattr(u, "start_ms", 0),
                getattr(u, "end_ms", 0),
                str(getattr(u, "speaker_label", getattr(u, "speaker", ""))),
            ),
        )

        first_start = getattr(sorted_utts[0], "start_ms", 0)
        last_end = max(getattr(u, "end_ms", 0) for u in sorted_utts)

        leading_uncovered_ms = max(0, first_start)
        transcribed_coverage_end_ms = last_end
        trailing_uncovered_ms = max(0, audio_duration_ms - last_end)
        has_uncovered_audio = (
            leading_uncovered_ms > self.coverage_tolerance_ms
            or trailing_uncovered_ms > self.coverage_tolerance_ms
        )

        # Group intervals by role
        agent_intervals: list[Interval] = []
        customer_intervals: list[Interval] = []
        all_intervals: list[Interval] = []

        agent_word_count = 0
        customer_word_count = 0

        for u in sorted_utts:
            start = getattr(u, "start_ms", 0)
            end = getattr(u, "end_ms", 0)
            if end <= start:
                continue

            iv = Interval(start_ms=start, end_ms=end)
            all_intervals.append(iv)

            # Determine role: check business_role, role_map, or speaker
            raw_speaker = str(getattr(u, "speaker_label", getattr(u, "speaker", "")))
            role = str(getattr(u, "business_role", role_map.get(raw_speaker, getattr(u, "speaker", "UNKNOWN"))))

            text = getattr(u, "text", "")
            words = [w for w in text.split() if w]
            word_count = len(words)

            if role == "AGENT":
                agent_intervals.append(iv)
                agent_word_count += word_count
            elif role == "CUSTOMER":
                customer_intervals.append(iv)
                customer_word_count += word_count

        agent_talk_ms = total_duration_ms(agent_intervals)
        customer_talk_ms = total_duration_ms(customer_intervals)
        total_speech_ms = total_duration_ms(all_intervals)

        agent_talk_pct = (
            round((agent_talk_ms / total_speech_ms) * 100.0, 2) if total_speech_ms > 0 else 0.0
        )
        customer_talk_pct = (
            round((customer_talk_ms / total_speech_ms) * 100.0, 2) if total_speech_ms > 0 else 0.0
        )
        occupancy_pct = (
            round((total_speech_ms / audio_duration_ms) * 100.0, 2) if audio_duration_ms > 0 else 0.0
        )

        agent_wpm = (
            round(agent_word_count / (agent_talk_ms / 60_000.0), 1) if agent_talk_ms > 0 else 0.0
        )
        customer_wpm = (
            round(customer_word_count / (customer_talk_ms / 60_000.0), 1)
            if customer_talk_ms > 0
            else 0.0
        )

        # 1. Internal dead-air gaps: gaps between merged speech intervals >= dead_air_threshold_ms
        dead_air_gaps: list[SilenceInterval] = []
        merged_speech = union_intervals(all_intervals)
        for i in range(len(merged_speech) - 1):
            gap_start = merged_speech[i].end_ms
            gap_end = merged_speech[i + 1].start_ms
            gap_dur = gap_end - gap_start
            if gap_dur >= self.dead_air_threshold_ms:
                dead_air_gaps.append(
                    SilenceInterval(start_ms=gap_start, end_ms=gap_end, duration_ms=gap_dur)
                )

        # 2. Interruption candidates: speaker B overlaps speaker A by > interruption_min_duration_ms
        interruption_candidates: list[InterruptionCandidate] = []
        for i in range(len(sorted_utts)):
            u1 = sorted_utts[i]
            s1 = getattr(u1, "speaker_label", getattr(u1, "speaker", ""))
            u1_start = getattr(u1, "start_ms", 0)
            u1_end = getattr(u1, "end_ms", 0)

            for j in range(i + 1, len(sorted_utts)):
                u2 = sorted_utts[j]
                u2_start = getattr(u2, "start_ms", 0)
                u2_end = getattr(u2, "end_ms", 0)
                s2 = getattr(u2, "speaker_label", getattr(u2, "speaker", ""))

                if u2_start >= u1_end:
                    break  # Sorted by start_ms, subsequent utterances won't overlap u1

                if s1 != s2 and u2_start > u1_start:
                    # u2 interrupts u1
                    overlap_end = min(u1_end, u2_end)
                    overlap_duration = overlap_end - u2_start
                    if overlap_duration >= self.interruption_min_duration_ms:
                        interruption_candidates.append(
                            InterruptionCandidate(
                                speaker_label=str(s2),
                                interrupted_speaker_label=str(s1),
                                start_ms=u2_start,
                                overlap_duration_ms=overlap_duration,
                            )
                        )

        # Sort interruption candidates deterministically
        interruption_candidates = sorted(
            interruption_candidates,
            key=lambda c: (c.start_ms, c.overlap_duration_ms, c.speaker_label),
        )

        return SpeechBehaviorMetrics(
            audio_duration_ms=audio_duration_ms,
            transcribed_coverage_end_ms=transcribed_coverage_end_ms,
            leading_uncovered_ms=leading_uncovered_ms,
            trailing_uncovered_ms=trailing_uncovered_ms,
            has_uncovered_audio=has_uncovered_audio,
            agent_talk_ms=agent_talk_ms,
            customer_talk_ms=customer_talk_ms,
            total_speech_ms=total_speech_ms,
            agent_talk_percentage=agent_talk_pct,
            customer_talk_percentage=customer_talk_pct,
            conversational_occupancy_percentage=occupancy_pct,
            agent_words_per_minute=agent_wpm,
            customer_words_per_minute=customer_wpm,
            dead_air_gaps=dead_air_gaps,
            interruption_candidates=interruption_candidates,
        )
