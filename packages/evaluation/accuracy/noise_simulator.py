"""ASR Noise Simulator — realistic Australian telephony transcription errors.

Models the kind of degradation that Whisper produces on noisy dialler audio so we can
measure how gracefully the evaluation engine handles it.  The invariant under test is:
**critical_false_passes must remain zero at any noise level**.  Corrupted disclosures must
degrade to AMBIGUOUS or FAIL, never silently pass.

Usage::

    from packages.evaluation.accuracy.noise_simulator import AsrNoiseSimulator

    sim = AsrNoiseSimulator(noise_level=0.10, seed=42)
    noisy_text = sim.corrupt(original_text)

The simulator is *deterministic* given the same seed, so test results are reproducible.
"""

import random
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Australian English phoneme confusion table
# Each tuple is (pattern, [alternatives]) where alternatives are plausible ASR
# transcription errors for Australian accents + telephony compression artefacts.
# ---------------------------------------------------------------------------

_PHONEME_CONFUSIONS: list[tuple[str, list[str]]] = [
    # "cents" / "cent" sounds like "sense" on low-quality lines
    (r"\bcents?\b", ["sense", "since"]),
    # "our" / "hour" homophone
    (r"\bhour\b", ["our"]),
    (r"\bour\b", ["hour"]),
    # cooling off period
    (r"\bcooling off\b", ["cooling of", "calling off", "cooling of the"]),
    # consent often misheard
    (r"\bconsent\b", ["content", "con sent", "consent"]),
    # explicit — "ex" swallowed on phone
    (r"\bexplicit\b", ["explicit", "implicit", "explicit"]),
    # "kilowatt" swallowed to "kilowat"
    (r"\bkilowatt hour\b", ["kilowatt our", "kilowatt hour", "kilowat our"]),
    (r"\bkilowatt-hour\b", ["kilowatt our", "kilowat hour"]),
    # "per" reduced on fast speech
    (r"\bper kilowatt\b", ["per kilowatt", "a kilowatt", "per kilowat"]),
    # "supply charge" → "supply chart" / "supply charge"
    (r"\bsupply charge\b", ["supply chart", "supply charge", "supply chai"]),
    # "default offer" → "default offer" (already OK) but can be "the fault offer"
    (r"\bdefault offer\b", ["the fault offer", "de fault offer", "default offer"]),
    # "reference price" → "reference price" / "reference prize"
    (r"\breference price\b", ["reference prize", "reference price"]),
    # "business day" → "business day" / "bizness day"
    (r"\bbusiness day\b", ["business day", "bizness day", "business days"]),
    # Decimal spoken numbers: "twenty-eight point six" → mishear of decimal
    (r"\btwenty[\s-]eight point six\b", ["twenty eight point six", "28.6", "twenty eight 0.6"]),
    (r"\bthirty[\s-]one point nine\b", ["thirty one point nine", "31.9", "thirty one nine"]),
    (r"\bforty[\s-]two\b", ["forty two", "42", "forty to"]),
    # NBN speed disclosures
    (r"\btwenty[\s-]five\s+[Mm]bps\b", ["twenty five mbps", "25mbps", "25 Mbps"]),
    (r"\beight point five\s+[Mm]bps\b", ["eight point five mbps", "8.5mbps"]),
    # EIC phrase key terms
    (r"\bcan I have your explicit informed consent\b",
     ["can I have your explicit in form consent", "can I have you explicit informed consent"]),
    (r"\bcooling[\s-]off period\b", ["cooling of period", "cooling off period", "cooling-of period"]),
    # "account holder" → "a count holder"
    (r"\baccount holder\b", ["a count holder", "account holder", "account older"]),
    # "life support" → "like support"
    (r"\blife support\b", ["like support", "life support"]),
    # Recording disclosure
    (r"\brecorded for quality\b", ["recorded for quality", "record it for quality", "recorded to quality"]),
    # Email domain mishears (critical: compliance checks email verbatim)
    (r"\bgmail\.com\b", ["gmail.com", "g mail.com", "gmail dot com"]),
    (r"\bhotmail\.com\b", ["hotmail.com", "hot mail.com"]),
    # Numbers: "sixty-five" → "65"
    (r"\bsixty[\s-]five\b", ["sixty five", "65", "sixty 5"]),
    (r"\bseventy[\s-]two\b", ["seventy two", "72", "seventy to"]),
]

# Compiled for efficiency
_COMPILED_CONFUSIONS: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(pattern, re.IGNORECASE), alternatives)
    for pattern, alternatives in _PHONEME_CONFUSIONS
]

# ---------------------------------------------------------------------------
# Australian English disfluency tokens
# ---------------------------------------------------------------------------
_DISFLUENCIES = [
    "um", "uh", "ah", "like", "you know", "sort of", "kind of",
    "right", "okay", "yeah", "so", "well", "I mean",
]

# Filler words that sound natural at the start of a clause
_FILLERS = ["uh", "um", "right,", "okay,", "so,", "well,"]


@dataclass
class NoiseReport:
    """Records what corruptions were applied, for test diagnostics."""

    phoneme_swaps: int = 0
    word_dropouts: int = 0
    disfluencies_injected: int = 0
    truncations: int = 0
    detail: list[str] = field(default_factory=list)


class AsrNoiseSimulator:
    """Injects realistic Australian telephony ASR errors into clean transcript text.

    Args:
        noise_level: Probability (0.0–1.0) of applying each individual noise
            category to each segment.  0.10 = 10 % — the brief's guardrail threshold.
        seed: Random seed for deterministic replay.
    """

    def __init__(self, noise_level: float = 0.10, seed: int | None = 42):
        if not 0.0 <= noise_level <= 1.0:
            raise ValueError(f"noise_level must be in [0,1], got {noise_level}")
        self.noise_level = noise_level
        self._rng = random.Random(seed)

    def corrupt(self, text: str) -> tuple[str, NoiseReport]:
        """Apply a stochastic mix of noise to *text*; return (noisy_text, report)."""
        report = NoiseReport()
        result = text

        # 1. Phoneme confusion substitutions
        result, report = self._apply_phoneme_confusions(result, report)

        # 2. Word dropout (packet loss / clipping)
        result, report = self._apply_word_dropout(result, report)

        # 3. Disfluency injection (filler words)
        result, report = self._apply_disfluencies(result, report)

        # 4. Trailing truncation (call ended before disclosure finished)
        result, report = self._apply_truncation(result, report)

        return result, report

    def corrupt_segments(
        self, segments: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[NoiseReport]]:
        """Apply noise to a list of segment dicts (each must have a ``"text"`` key).

        Returns the corrupted segment list and per-segment reports.
        """
        corrupted = []
        reports = []
        for seg in segments:
            noisy_text, report = self.corrupt(seg["text"])
            corrupted.append({**seg, "text": noisy_text})
            reports.append(report)
        return corrupted, reports

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_phoneme_confusions(self, text: str, report: NoiseReport) -> tuple[str, NoiseReport]:
        """Replace phrases with phonetically plausible ASR alternatives."""
        for pattern, alternatives in _COMPILED_CONFUSIONS:
            if self._rng.random() < self.noise_level:
                match = pattern.search(text)
                if match:
                    replacement = self._rng.choice(alternatives)
                    text = text[:match.start()] + replacement + text[match.end():]
                    if replacement.lower() != match.group(0).lower():
                        report.phoneme_swaps += 1
                        report.detail.append(
                            f"phoneme: '{match.group(0)}' → '{replacement}'"
                        )
        return text, report

    def _apply_word_dropout(self, text: str, report: NoiseReport) -> tuple[str, NoiseReport]:
        """Randomly drop words to simulate packet loss or clipping."""
        words = text.split()
        if len(words) < 4:
            return text, report
        kept = []
        dropped = 0
        for word in words:
            if self._rng.random() < self.noise_level * 0.5:
                dropped += 1
                report.detail.append(f"dropout: '{word}'")
            else:
                kept.append(word)
        if dropped:
            report.word_dropouts += dropped
        return " ".join(kept), report

    def _apply_disfluencies(self, text: str, report: NoiseReport) -> tuple[str, NoiseReport]:
        """Insert filler words at clause boundaries."""
        if self._rng.random() > self.noise_level:
            return text, report
        sentences = re.split(r"([.!?,])", text)
        result_parts = []
        injected = 0
        for part in sentences:
            result_parts.append(part)
            # Inject a disfluency after a comma or in the middle of a long clause
            if self._rng.random() < self.noise_level and len(part.split()) > 5:
                filler = self._rng.choice(_DISFLUENCIES)
                words = part.split()
                insert_at = self._rng.randint(1, max(1, len(words) - 1))
                words.insert(insert_at, filler)
                result_parts[-1] = " ".join(words)
                injected += 1
        if injected:
            report.disfluencies_injected += injected
        return "".join(result_parts), report

    def _apply_truncation(self, text: str, report: NoiseReport) -> tuple[str, NoiseReport]:
        """Truncate the last few words with very low probability (call-end clipping)."""
        # Only truncate at very low probability even within the noise level
        if self._rng.random() > self.noise_level * 0.3:
            return text, report
        words = text.split()
        if len(words) < 8:
            return text, report
        keep = self._rng.randint(int(len(words) * 0.70), len(words) - 1)
        truncated = " ".join(words[:keep]) + "..."
        report.truncations += 1
        report.detail.append(f"truncated: kept {keep}/{len(words)} words")
        return truncated, report
