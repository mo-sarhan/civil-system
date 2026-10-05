"""Unit tests for the Arabic and national-ID helpers."""

from __future__ import annotations

import pytest

from app.utils.arabic import (
    full_name_key,
    name_tokens,
    normalize_name,
    parse_full_name,
    similarity,
    to_arabic_digits,
    to_ascii_digits,
)
from app.utils.national_id import (
    NationalIdInfo,
    is_valid_national_id,
    mask_national_id,
    parse_national_id,
)


class TestNormalizeName:
    def test_strips_tashkeel_and_collapses_spaces(self) -> None:
        assert normalize_name("مُحَمَّد   أحمد  السيد") == "محمد احمد السيد"

    def test_normalizes_alef_forms_and_hamza(self) -> None:
        assert normalize_name("إبراهيم آمنة") == "ابراهيم امنه"

    def test_converts_arabic_indic_digits(self) -> None:
        assert normalize_name("أحمد ٥") == "احمد 5"

    def test_punctuation_becomes_a_single_space(self) -> None:
        assert normalize_name("محمد-أحمد/ السيد") == "محمد احمد السيد"

    def test_empty_and_none(self) -> None:
        assert normalize_name(None) == ""
        assert normalize_name("   ") == ""

    def test_keeps_latin_letters(self) -> None:
        assert normalize_name("Omar Ahmed") == "omar ahmed"


class TestDigits:
    def test_to_ascii_digits(self) -> None:
        assert to_ascii_digits("٤٢") == "42"

    def test_to_arabic_digits(self) -> None:
        assert to_arabic_digits("42") == "٤٢"


class TestTokensAndKeys:
    def test_name_tokens_normalize_and_drop_blanks(self) -> None:
        assert name_tokens("  مُحَمَّد   أحمد ") == ["محمد", "احمد"]

    def test_full_name_key_is_order_independent(self) -> None:
        assert full_name_key("السيد أحمد محمد") == full_name_key("محمد أحمد السيد")

    def test_similarity_of_identical_names(self) -> None:
        assert similarity("محمد احمد", "محمد احمد") == pytest.approx(1.0)

    def test_similarity_of_unrelated_names_is_low(self) -> None:
        assert similarity("محمد احمد", "سعاد محمود") < 0.5


class TestParseFullName:
    def test_four_units_fill_every_part(self) -> None:
        assert parse_full_name("محمد أحمد السيد Willy") == {
            "first_name": "محمد",
            "father_name": "أحمد",
            "grandfather_name": "السيد",
            "family_name": "Willy",
        }

    def test_particle_stays_glued_to_its_token(self) -> None:
        parts = parse_full_name("محمد أحمد عبد الله السيد")
        assert parts["grandfather_name"] == "عبد الله"
        assert parts["family_name"] == "السيد"

    def test_particle_can_start_the_name(self) -> None:
        parts = parse_full_name("أبو بكر عبد الله الرشيد")
        assert parts["first_name"] == "أبو بكر"
        assert parts["father_name"] == "عبد الله"
        assert parts["family_name"] == "الرشيد"

    def test_two_tokens_leave_the_middle_empty(self) -> None:
        parts = parse_full_name("محمود السيد")
        assert parts["first_name"] == "محمود"
        assert parts["family_name"] == "السيد"
        assert parts["father_name"] is None

    def test_empty_input(self) -> None:
        assert parse_full_name("") == {
            "first_name": None,
            "father_name": None,
            "grandfather_name": None,
            "family_name": None,
        }


class TestNationalId:
    def test_valid_male_id(self) -> None:
        parsed = parse_national_id("24003151200113")
        assert isinstance(parsed, NationalIdInfo)
        assert parsed.birth_date.isoformat() == "1940-03-15"
        assert parsed.gender == "M"
        # digits 8-9 carry the issuing governorate
        assert parsed.governorate_code == "12"
        assert parsed.governorate_name == "سوهاج"

    def test_valid_female_id(self) -> None:
        parsed = parse_national_id("24507201200224")
        assert parsed.gender == "F"
        assert parsed.birth_date.isoformat() == "1945-07-20"

    def test_century_prefix_picks_the_era(self) -> None:
        assert parse_national_id("24003151200113").birth_date.year == 1940
        assert parse_national_id("30003151200113").birth_date.year == 2000

    def test_rejects_wrong_length(self) -> None:
        assert parse_national_id("2400315120011") is None
        assert parse_national_id("240031512001133") is None
        assert not is_valid_national_id("")

    def test_rejects_non_digits(self) -> None:
        assert parse_national_id("2400315120A113") is None

    def test_rejects_impossible_date(self) -> None:
        assert parse_national_id("24133251200111") is None

    def test_masking_keeps_only_the_last_four_digits(self) -> None:
        masked = mask_national_id("24003151200113")
        assert len(masked) == 14
        assert masked == "*" * 10 + "0113"
        assert "400315" not in masked

    def test_masking_short_values(self) -> None:
        assert mask_national_id("123") == "***"

    def test_masking_passes_through_empty(self) -> None:
        assert mask_national_id(None) in (None, "")
