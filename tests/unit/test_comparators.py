"""Unit tests for spoken-value extraction and comparison primitives."""

from datetime import date
from decimal import Decimal

import pytest

from packages.evaluation.comparators import (
    ComparatorType,
    compare_values,
    extract_boolean,
    extract_dates,
    extract_emails,
    extract_identifiers,
    extract_spoken_numbers,
    resolve_expected_value,
)


class TestSpokenNumberExtraction:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("peak is 28.6 cents", [Decimal("28.6")]),
            ("your peak rate is twenty eight point six cents", [Decimal("28.6")]),
            ("thirty one point nine cents per kilowatt hour", [Decimal("31.9")]),
            ("that is forty two point nine zero a month", [Decimal("42.90")]),
            ("28 point 6 cents", [Decimal("28.6")]),
            ("one hundred and fifteen point five cents daily", [Decimal("115.5")]),
        ],
    )
    def test_extracts_digit_and_word_forms(self, text, expected):
        assert extract_spoken_numbers(text) == expected

    def test_preserves_statement_order_for_multiple_values(self):
        text = "peak is 28.6 cents, off peak 22.1 cents, supply 115.5 cents"
        assert extract_spoken_numbers(text) == [
            Decimal("28.6"),
            Decimal("22.1"),
            Decimal("115.5"),
        ]

    def test_returns_empty_when_no_numbers_present(self):
        assert extract_spoken_numbers("thanks for your time today") == []


class TestEmailExtraction:
    def test_extracts_literal_email(self):
        assert extract_emails("is that j.smith@gmial.com") == ["j.smith@gmial.com"]

    def test_reconstructs_dictated_email(self):
        assert extract_emails("j dot smith at gmail dot com") == ["j.smith@gmail.com"]

    def test_reconstructs_dictated_email_with_underscore(self):
        assert extract_emails("jane underscore doe at outlook dot com") == [
            "jane_doe@outlook.com"
        ]


class TestDateExtraction:
    @pytest.mark.parametrize(
        "text",
        [
            "born on the 12th of March 1985",
            "DOB 12/03/1985",
            "date of birth 1985-03-12",
            "March 12, 1985",
        ],
    )
    def test_parses_common_date_forms(self, text):
        assert date(1985, 3, 12) in extract_dates(text)


class TestIdentifierExtraction:
    def test_extracts_nmi(self):
        assert "6305123456" in extract_identifiers("your NMI is 6305123456")

    def test_tolerates_dictated_spacing(self):
        assert "6305123456" in extract_identifiers("NMI 63051 23456")

    def test_rejects_ordinary_words(self):
        # Run-together prose must not be mistaken for a meter identifier.
        assert extract_identifiers("comparison service representative") == []


class TestBooleanExtraction:
    def test_affirmative(self):
        assert extract_boolean("yes that is correct") is True

    def test_negative_wins_over_affirmative_substring(self):
        assert extract_boolean("no, not at all") is False

    def test_returns_none_when_ambiguous(self):
        assert extract_boolean("let me check that for you") is None


class TestFieldResolution:
    def test_resolves_dotted_path(self):
        sources = [("SALE", {"details": {"tariff_peak_c_kwh": 31.9}})]
        value, label = resolve_expected_value(sources, ["details.tariff_peak_c_kwh"])
        assert value == 31.9
        assert label == "SALE.details.tariff_peak_c_kwh"

    def test_falls_through_to_second_source(self):
        sources = [("SALE", {"details": {}}), ("LEAD", {"customer_email": "a@b.com"})]
        value, label = resolve_expected_value(sources, ["customer_email"])
        assert value == "a@b.com"
        assert label == "LEAD.customer_email"

    def test_returns_none_when_unresolvable(self):
        value, label = resolve_expected_value([("SALE", {})], ["details.nmi"])
        assert value is None
        assert label is None


class TestComparison:
    def test_decimal_mismatch_outside_tolerance(self):
        outcome = compare_values(ComparatorType.DECIMAL, "31.9", Decimal("28.6"))
        assert outcome.matched is False
        assert outcome.near_miss is False

    def test_decimal_match_within_tolerance(self):
        outcome = compare_values(
            ComparatorType.DECIMAL, "31.9", Decimal("31.95"), tolerance=Decimal("0.05")
        )
        assert outcome.matched is True

    def test_email_typo_is_a_near_miss_not_a_match(self):
        outcome = compare_values(
            ComparatorType.EMAIL, "j.smith@gmail.com", "j.smith@gmial.com"
        )
        assert outcome.matched is False
        assert outcome.near_miss is True

    def test_identifier_ignores_dictation_spacing(self):
        outcome = compare_values(ComparatorType.IDENTIFIER, "6305123456", "6305 123 456")
        assert outcome.matched is True

    def test_boolean_mismatch(self):
        outcome = compare_values(ComparatorType.BOOLEAN, False, True)
        assert outcome.matched is False

    def test_date_match_across_formats(self):
        outcome = compare_values(ComparatorType.DATE, "1985-03-12", date(1985, 3, 12))
        assert outcome.matched is True
