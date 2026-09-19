"""PCI-DSS credit card number detection and masking via Luhn checksum verification."""

import re

# Matches candidate card number sequences: 13 to 19 digits with optional spaces or dashes
CARD_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def is_luhn_valid(card_number: str) -> bool:
    """Validate a digit sequence using the ISO/IEC 7812-1 Luhn mod-10 algorithm."""
    digits = [int(c) for c in card_number if c.isdigit()]
    if not (13 <= len(digits) <= 19):
        return False

    checksum = 0
    parity = (len(digits) - 2) % 2
    for i in range(len(digits) - 1, -1, -1):
        d = digits[i]
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d

    return checksum % 10 == 0


def mask_card_number(matched_str: str) -> str:
    """Masks card number preserving only the last 4 digits if Luhn check passes."""
    digits = [c for c in matched_str if c.isdigit()]
    digit_str = "".join(digits)

    if not is_luhn_valid(digit_str):
        return matched_str  # Not a valid credit card, do not mask

    last_4 = digit_str[-4:]
    return f"************{last_4}"


def redact_pci_text(text: str | None) -> str:
    """Scans text and replaces any verified Luhn payment card numbers with masked tokens."""
    if not text:
        return text or ""

    def _replacer(match: re.Match) -> str:
        return mask_card_number(match.group(0))

    return CARD_PATTERN.sub(_replacer, text)
