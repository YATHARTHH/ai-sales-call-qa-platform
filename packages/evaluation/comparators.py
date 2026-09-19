"""Deterministic value extraction, normalization, and comparison primitives for Tier B factual checks.

This module is intentionally free of any hardcoded business expectation. Every expected value
must be resolved from the immutable sale/lead snapshot or from explicit check parameters. When a
value cannot be resolved the caller must surface NOT_EVALUABLE so the deterministic gate holds
the sale, rather than comparing speech against a fabricated benchmark.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from enum import StrEnum
from typing import Any

# --------------------------------------------------------------------------------------
# Field resolution
# --------------------------------------------------------------------------------------

MISSING = object()


def resolve_field_path(source: Any, path: str) -> Any:
    """Resolve a dotted path (``details.tariff_peak_c_kwh``) inside nested dicts.

    Returns the sentinel ``MISSING`` when any segment is absent, so a legitimately stored
    ``None`` stays distinguishable from an unresolvable path.
    """
    current = source
    for segment in path.split("."):
        if isinstance(current, dict) and segment in current:
            current = current[segment]
        else:
            return MISSING
    return current


def resolve_expected_value(
    sources: Sequence[tuple[str, Any]],
    paths: Sequence[str],
) -> tuple[Any, str | None]:
    """Resolve the first usable value across candidate sources and dotted paths.

    Returns ``(value, source_label)``; ``(None, None)`` when nothing resolves.
    """
    for label, source in sources:
        for path in paths:
            value = resolve_field_path(source, path)
            if value is not MISSING and value is not None and value != "":
                return value, f"{label}.{path}"
    return None, None


# --------------------------------------------------------------------------------------
# Spoken-number normalization (ASR emits both "28.6" and "twenty eight point six")
# --------------------------------------------------------------------------------------

_UNITS = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000}
_FRACTION_MARKERS = {"point", "dot"}
_NUMBER_WORDS = set(_UNITS) | set(_TENS) | set(_SCALES) | _FRACTION_MARKERS | {"and"}


def _words_to_integer(words: list[str]) -> int | None:
    """Convert a run of English number words into an integer. Returns None if unparseable."""
    if not words:
        return None
    total = 0
    current = 0
    consumed = False
    for word in words:
        if word == "and":
            continue
        if word in _UNITS:
            current += _UNITS[word]
            consumed = True
        elif word in _TENS:
            current += _TENS[word]
            consumed = True
        elif word in _SCALES:
            scale = _SCALES[word]
            if current == 0:
                current = 1
            if scale == 100:
                current *= scale
            else:
                total += current * scale
                current = 0
            consumed = True
        else:
            return None
    return (total + current) if consumed else None


def _spoken_fraction(words: list[str]) -> tuple[str, int]:
    """Convert words after 'point' into a fraction string. Returns (digits, words_consumed)."""
    digits: list[str] = []
    consumed = 0
    for word in words:
        if word in _UNITS and _UNITS[word] <= 9:
            digits.append(str(_UNITS[word]))
            consumed += 1
        elif word in _TENS:
            # "point twenty five" is spoken shorthand for .25
            digits.append(str(_TENS[word]))
            consumed += 1
        else:
            break
    return "".join(digits), consumed


def extract_spoken_numbers(text: str) -> list[Decimal]:
    """Extract every numeric quantity from text, in spoken-word or digit form, in order."""
    results: list[Decimal] = []
    normalized = text.lower().replace(",", "")
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", normalized)

    index = 0
    while index < len(tokens):
        token = tokens[index]

        # Digit form, possibly followed by a spoken or digit fraction ("28 point 6")
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            literal = token
            if (
                "." not in literal
                and index + 1 < len(tokens)
                and tokens[index + 1] in _FRACTION_MARKERS
            ):
                tail = tokens[index + 2 : index + 8]
                if tail and re.fullmatch(r"\d+", tail[0]):
                    literal = f"{literal}.{tail[0]}"
                    index += 2
                else:
                    fraction, consumed = _spoken_fraction(tail)
                    if fraction:
                        literal = f"{literal}.{fraction}"
                        index += 1 + consumed
            try:
                results.append(Decimal(literal))
            except InvalidOperation:
                pass
            index += 1
            continue

        # Word form
        if token in _NUMBER_WORDS and token not in _FRACTION_MARKERS and token != "and":
            run_end = index
            while run_end < len(tokens) and tokens[run_end] in _NUMBER_WORDS:
                run_end += 1
            run = tokens[index:run_end]

            marker_index = next(
                (i for i, word in enumerate(run) if word in _FRACTION_MARKERS), None
            )
            if marker_index is not None:
                whole = _words_to_integer(run[:marker_index])
                fraction, _ = _spoken_fraction(run[marker_index + 1 :])
                if whole is not None:
                    literal = f"{whole}.{fraction}" if fraction else str(whole)
                    try:
                        results.append(Decimal(literal))
                    except InvalidOperation:
                        pass
            else:
                whole = _words_to_integer(run)
                if whole is not None:
                    results.append(Decimal(whole))
            index = run_end
            continue

        index += 1

    return results


# --------------------------------------------------------------------------------------
# Spoken-email normalization ("j dot smith at gmail dot com")
# --------------------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

_SPOKEN_EMAIL_SUBSTITUTIONS = [
    (r"\s+at\s+the\s+rate\s+of\s+", "@"),
    (r"\s+at\s+sign\s+", "@"),
    (r"\s+at\s+", "@"),
    (r"\s+dot\s+", "."),
    (r"\s+full\s+stop\s+", "."),
    (r"\s+period\s+", "."),
    (r"\s+underscore\s+", "_"),
    (r"\s+under\s+score\s+", "_"),
    (r"\s+hyphen\s+", "-"),
    (r"\s+dash\s+", "-"),
]


def extract_emails(text: str) -> list[str]:
    """Extract emails written literally or dictated phonetically."""
    found = [match.lower() for match in _EMAIL_PATTERN.findall(text)]
    if found:
        return found

    spoken = text.lower()
    for pattern, replacement in _SPOKEN_EMAIL_SUBSTITUTIONS:
        spoken = re.sub(pattern, replacement, spoken)
    # Tighten spacing around the separators only. Collapsing every space would weld the
    # preceding sentence onto the local part ("as john.smith@..." -> "asjohn.smith@...").
    spoken = re.sub(r"\s*([@._-])\s*", r"\1", spoken)
    return [match.lower() for match in _EMAIL_PATTERN.findall(spoken)]


# --------------------------------------------------------------------------------------
# Identifier, date and boolean extraction
# --------------------------------------------------------------------------------------


def extract_identifiers(text: str, min_length: int = 10, max_length: int = 11) -> list[str]:
    """Extract NMI / MIRN style identifiers, tolerating spaces between dictated characters.

    Candidates must be mostly numeric; utility identifiers are digit-dominant, and requiring
    this keeps ordinary run-together words out of the candidate set.
    """
    def is_identifier_shaped(value: str) -> bool:
        # At least four digits keeps ordinary words out; the length bounds do the rest. Candidates
        # are always whole spoken tokens, so no further digit-density rule is needed.
        return (
            min_length <= len(value) <= max_length
            and sum(character.isdigit() for character in value) >= 4
        )

    candidates: set[str] = set()
    tokens = re.findall(r"[A-Za-z0-9]+", text.upper())

    # A whole spoken token, e.g. "6102123456".
    for token in tokens:
        if is_identifier_shaped(token):
            candidates.add(token)

    # An identifier dictated in groups, e.g. "63051 23456". Consecutive tokens that each contain a
    # digit are joined; tokens are never split or partially consumed, so surrounding words can
    # never be glued onto the number.
    run: list[str] = []
    for token in tokens + [""]:
        if token and any(character.isdigit() for character in token):
            run.append(token)
            continue
        if len(run) > 1 and is_identifier_shaped("".join(run)):
            candidates.add("".join(run))
        run = []

    return sorted(candidates)


_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), ("y", "m", "d")),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), ("d", "m", "y")),
    (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"), ("d", "m", "y")),
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_ORDINAL_SUFFIX = re.compile(r"(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_SPOKEN_DATE = re.compile(
    r"\b(\d{1,2})\s+(?:of\s+)?([a-z]+)\s+(\d{4})\b|\b([a-z]+)\s+(\d{1,2})\s*,?\s+(\d{4})\b"
)


def extract_dates(text: str) -> list[date]:
    """Extract dates in numeric or spoken form ('12th of March 1985')."""
    results: list[date] = []
    for pattern, order in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            parts = dict(zip(order, match.groups(), strict=True))
            try:
                results.append(date(int(parts["y"]), int(parts["m"]), int(parts["d"])))
            except (ValueError, KeyError):
                continue

    cleaned = _ORDINAL_SUFFIX.sub(r"\1", text.lower())
    for match in _SPOKEN_DATE.finditer(cleaned):
        if match.group(1):
            day, month_word, year = match.group(1), match.group(2), match.group(3)
        else:
            month_word, day, year = match.group(4), match.group(5), match.group(6)
        month = _MONTHS.get(month_word)
        if not month:
            continue
        try:
            results.append(date(int(year), month, int(day)))
        except ValueError:
            continue
    return results


_AFFIRMATIVE = ["yes", "yeah", "yep", "correct", "that's right", "affirmative", "i do", "sure"]
_NEGATIVE = ["no", "nope", "negative", "i don't", "i do not", "not at all"]


def extract_boolean(text: str) -> bool | None:
    """Resolve an explicit affirmative/negative confirmation from a spoken response."""
    normalized = re.sub(r"[^\w\s']", " ", text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    for phrase in _NEGATIVE:
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            return False
    for phrase in _AFFIRMATIVE:
        if re.search(rf"\b{re.escape(phrase)}\b", normalized):
            return True
    return None


# --------------------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------------------


class ComparatorType(StrEnum):
    DECIMAL = "DECIMAL"
    MONEY = "MONEY"
    EMAIL = "EMAIL"
    DATE = "DATE"
    TEXT = "TEXT"
    IDENTIFIER = "IDENTIFIER"
    BOOLEAN = "BOOLEAN"


@dataclass(frozen=True)
class ComparisonOutcome:
    """Result of comparing one observed spoken value to the authoritative expected value."""

    matched: bool
    near_miss: bool
    similarity: float
    detail: str


def normalize_text(value: str) -> str:
    text = value.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def coerce_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).strip().replace("$", "").replace(",", ""))
    except (InvalidOperation, AttributeError, ValueError):
        return None


def coerce_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    parsed = extract_dates(text)
    return parsed[0] if parsed else None


def coerce_boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "y"):
        return True
    if text in ("false", "0", "no", "n"):
        return False
    return None


def compare_values(
    comparator: ComparatorType,
    expected: Any,
    observed: Any,
    tolerance: Decimal = Decimal("0"),
    near_miss_threshold: float = 0.85,
) -> ComparisonOutcome:
    """Compare an observed spoken value against the authoritative expected value.

    ``near_miss`` marks an observation close enough to the expectation that it is most likely a
    transcription artefact rather than a genuine compliance breach; callers downgrade these to
    AMBIGUOUS so a human adjudicates instead of a false critical being manufactured.
    """
    if comparator in (ComparatorType.DECIMAL, ComparatorType.MONEY):
        expected_decimal = coerce_decimal(expected)
        observed_decimal = coerce_decimal(observed)
        if expected_decimal is None or observed_decimal is None:
            return ComparisonOutcome(False, False, 0.0, "Value could not be parsed as a number.")
        variance = abs(observed_decimal - expected_decimal)
        matched = variance <= tolerance
        unit = "$" if comparator is ComparatorType.MONEY else ""
        return ComparisonOutcome(
            matched=matched,
            near_miss=False,
            similarity=1.0 if matched else 0.0,
            detail=(
                f"Spoken {unit}{observed_decimal} compared to expected {unit}{expected_decimal} "
                f"(variance {variance}, tolerance {tolerance})."
            ),
        )

    if comparator is ComparatorType.EMAIL:
        expected_text = str(expected).strip().lower()
        observed_text = str(observed).strip().lower()
        matched = expected_text == observed_text
        similarity = SequenceMatcher(None, expected_text, observed_text).ratio()
        return ComparisonOutcome(
            matched=matched,
            near_miss=not matched and similarity >= near_miss_threshold,
            similarity=round(similarity, 4),
            detail=(
                "Spoken email matches the CRM record."
                if matched
                else f"Spoken '{observed_text}' does not match CRM '{expected_text}'."
            ),
        )

    if comparator is ComparatorType.DATE:
        expected_date = coerce_date(expected)
        observed_date = coerce_date(observed)
        if expected_date is None or observed_date is None:
            return ComparisonOutcome(False, False, 0.0, "Value could not be parsed as a date.")
        matched = expected_date == observed_date
        return ComparisonOutcome(
            matched=matched,
            near_miss=False,
            similarity=1.0 if matched else 0.0,
            detail=f"Spoken date {observed_date.isoformat()} vs CRM {expected_date.isoformat()}.",
        )

    if comparator is ComparatorType.IDENTIFIER:
        expected_text = re.sub(r"[\s\-]", "", str(expected).upper())
        observed_text = re.sub(r"[\s\-]", "", str(observed).upper())
        matched = expected_text == observed_text
        similarity = SequenceMatcher(None, expected_text, observed_text).ratio()
        return ComparisonOutcome(
            matched=matched,
            near_miss=not matched and similarity >= near_miss_threshold,
            similarity=round(similarity, 4),
            detail=f"Spoken identifier '{observed_text}' vs CRM '{expected_text}'.",
        )

    if comparator is ComparatorType.BOOLEAN:
        expected_bool = coerce_boolean(expected)
        observed_bool = coerce_boolean(observed)
        if expected_bool is None or observed_bool is None:
            return ComparisonOutcome(False, False, 0.0, "Value could not be parsed as a boolean.")
        matched = expected_bool == observed_bool
        return ComparisonOutcome(
            matched=matched,
            near_miss=False,
            similarity=1.0 if matched else 0.0,
            detail=f"Confirmed '{observed_bool}' vs CRM '{expected_bool}'.",
        )

    # Free text is compared by containment, not equality: the observed value is a whole spoken
    # utterance and the CRM value is the fragment that has to appear inside it. "Your supply
    # address is 12 Rose Street" confirms "12 Rose Street"; comparing the two in full would
    # manufacture a failure out of the surrounding words.
    expected_text = normalize_text(str(expected))
    observed_text = normalize_text(str(observed))

    if not expected_text:
        return ComparisonOutcome(False, False, 0.0, "Expected text was empty.")

    if expected_text in observed_text:
        return ComparisonOutcome(
            matched=True,
            near_miss=False,
            similarity=1.0,
            detail=f"CRM value '{expected_text}' was confirmed within the spoken utterance.",
        )

    similarity = best_partial_similarity(expected_text, observed_text)
    return ComparisonOutcome(
        matched=False,
        near_miss=similarity >= near_miss_threshold,
        similarity=round(similarity, 4),
        detail=(
            f"CRM value '{expected_text}' was not confirmed in '{observed_text}' "
            f"(closest match {similarity:.2f})."
        ),
    )


def best_partial_similarity(needle: str, haystack: str) -> float:
    """Best similarity between ``needle`` and any same-length window of ``haystack``.

    Used so a short CRM value is scored against the part of the utterance that actually
    corresponds to it rather than against the whole sentence.
    """
    if not needle or not haystack:
        return 0.0
    if len(haystack) <= len(needle):
        return SequenceMatcher(None, needle, haystack).ratio()

    matcher = SequenceMatcher(None, needle, haystack)
    best = matcher.ratio()
    window = len(needle)
    for start in range(0, len(haystack) - window + 1):
        ratio = SequenceMatcher(None, needle, haystack[start : start + window]).ratio()
        if ratio > best:
            best = ratio
    return best
