"""Unit tests for pure domain speech behavior metrics math and interval unions."""


from packages.domain.speech_metrics import (
    Interval,
    SpeechBehaviorAnalyzer,
    total_duration_ms,
    union_intervals,
)


class DummyUtterance:
    def __init__(self, speaker_label: str, start_ms: int, end_ms: int, text: str):
        self.speaker_label = speaker_label
        self.start_ms = start_ms
        self.end_ms = end_ms
        self.text = text


def test_union_intervals_merges_overlaps_accurately():
    """Overlapping intervals must merge without double-counting talk time."""
    # Utterances: [1000, 3000] and [2000, 5000] and [6000, 7000]
    intervals = [
        Interval(1000, 3000),
        Interval(2000, 5000),
        Interval(6000, 7000),
    ]
    merged = union_intervals(intervals)

    assert len(merged) == 2
    assert merged[0] == Interval(1000, 5000)  # 4000 ms duration
    assert merged[1] == Interval(6000, 7000)  # 1000 ms duration
    assert total_duration_ms(intervals) == 5000  # Not 2000 + 3000 + 1000 = 6000


def test_speech_metrics_internal_dead_air_detection():
    """Internal gaps >= 45,000 ms between utterances are emitted as dead air."""
    analyzer = SpeechBehaviorAnalyzer(dead_air_threshold_ms=45_000)

    utterances = [
        DummyUtterance("SPEAKER_00", 2000, 10000, "First utterance by agent."),
        # 47-second gap: 10,000 ms to 57,000 ms = 47,000 ms gap
        DummyUtterance("SPEAKER_00", 57000, 65000, "Agent resumes after long hold."),
        # 10-second gap: 65,000 ms to 75,000 ms = 10,000 ms (not dead air)
        DummyUtterance("SPEAKER_01", 75000, 80000, "Customer responds."),
    ]
    metrics = analyzer.analyze(
        utterances=utterances,
        audio_duration_ms=100000,
        role_mapping={"SPEAKER_00": "AGENT", "SPEAKER_01": "CUSTOMER"},
    )

    assert len(metrics.dead_air_gaps) == 1
    assert metrics.dead_air_gaps[0].start_ms == 10000
    assert metrics.dead_air_gaps[0].end_ms == 57000
    assert metrics.dead_air_gaps[0].duration_ms == 47000


def test_speech_metrics_boundary_silence_not_dead_air():
    """Leading and trailing silence are coverage observations, not conversational dead air."""
    analyzer = SpeechBehaviorAnalyzer(dead_air_threshold_ms=45_000, coverage_tolerance_ms=5000)

    # Call starts at 0, first speech at 20,000 ms (20s leading silence)
    # Last speech ends at 80,000 ms, call ends at 110,000 ms (30s trailing silence)
    utterances = [
        DummyUtterance("SPEAKER_00", 20000, 40000, "Hello agent here."),
        DummyUtterance("SPEAKER_01", 42000, 80000, "Customer speaking."),
    ]
    metrics = analyzer.analyze(
        utterances=utterances,
        audio_duration_ms=110000,
        role_mapping={"SPEAKER_00": "AGENT", "SPEAKER_01": "CUSTOMER"},
    )

    # Dead air gaps list must be empty because internal gap is only 2s
    assert len(metrics.dead_air_gaps) == 0

    # Boundary metrics correctly observed
    assert metrics.leading_uncovered_ms == 20000
    assert metrics.transcribed_coverage_end_ms == 80000
    assert metrics.trailing_uncovered_ms == 30000
    assert metrics.has_uncovered_audio is True


def test_speech_metrics_interruption_detection():
    """Overlaps > 500 ms where speaker B starts after speaker A are flagged as interruption candidates."""
    analyzer = SpeechBehaviorAnalyzer(interruption_min_duration_ms=500)

    utterances = [
        # Agent speaks from 1000 to 5000 ms
        DummyUtterance("SPEAKER_00", 1000, 5000, "I am explaining the complete contract details."),
        # Customer interrupts at 3000 ms and speaks until 4500 ms (1500 ms overlap > 500 ms)
        DummyUtterance("SPEAKER_01", 3000, 4500, "Wait, what about the rate?"),
        # Short overlap of 200 ms (less than 500 ms threshold)
        DummyUtterance("SPEAKER_00", 6000, 8000, "Continuing..."),
        DummyUtterance("SPEAKER_01", 7800, 8500, "Yeah."),
    ]
    metrics = analyzer.analyze(
        utterances=utterances,
        audio_duration_ms=10000,
        role_mapping={"SPEAKER_00": "AGENT", "SPEAKER_01": "CUSTOMER"},
    )

    assert len(metrics.interruption_candidates) == 1
    candidate = metrics.interruption_candidates[0]
    assert candidate.speaker_label == "SPEAKER_01"
    assert candidate.interrupted_speaker_label == "SPEAKER_00"
    assert candidate.start_ms == 3000
    assert candidate.overlap_duration_ms == 1500


def test_speech_metrics_active_speech_wpm():
    """Words per minute is computed using speech talk time, not total call duration."""
    analyzer = SpeechBehaviorAnalyzer()

    # Agent speaks 120 words across exactly 60,000 ms (1 minute) of agent talk time
    words = "word " * 120
    utterances = [
        DummyUtterance("SPEAKER_00", 10000, 70000, words.strip()),
    ]
    # Total call is 600,000 ms (10 minutes)
    metrics = analyzer.analyze(
        utterances=utterances,
        audio_duration_ms=600000,
        role_mapping={"SPEAKER_00": "AGENT"},
    )

    # 120 words / 1.0 minute = 120 WPM (NOT 120 words / 10 minutes = 12 WPM)
    assert metrics.agent_words_per_minute == 120.0
    assert metrics.agent_talk_ms == 60000
    assert metrics.conversational_occupancy_percentage == 10.0
