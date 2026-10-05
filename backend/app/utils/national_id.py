"""Egyptian national ID (رقم القومى) validation.

Format (14 digits)::

    2 5 0 2 1 0 1 2 0 0 3 1 1 5
    ^ ^^^^^^^ ^^ ^^^ ^ ^
    | |      |  |   | |
    | |      |  |   | gender digit (odd = male, even = female)
    | |      |  |   checksum (not validated - no public algorithm)
    | |      |  governorate code
    | YYMMDD
    century (2 = 1900s, 3 = 2000s)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.utils.messages import Messages

#: Egyptian governorate codes as used in positions 8-9 of the national ID.
GOVERNORATE_CODES: dict[str, str] = {
    "01": "القاهرة",
    "02": "القاهرة",
    "03": "القاهرة",
    "04": "القاهرة",
    "05": "القاهرة",
    "11": "سوهاج",
    "12": "سوهاج",
    "13": "أسيوط",
    "14": "أسيوط",
    "15": "أسيوط",
    "16": "أسيوط",
    "17": "بني سويف",
    "18": "بني سويف",
    "19": "بني سويف",
    "20": "بني سويف",
    "21": "الفيوم",
    "22": "الفيوم",
    "23": "الفيوم",
    "24": "بورسعيد",
    "25": "بورسعيد",
    "26": "بورسعيد",
    "27": "دمياط",
    "28": "دمياط",
    "29": "دمياط",
    "30": "الزقازيق",
    "31": "الزقازيق",
    "32": "الزقازيق",
    "33": "بنها",
    "34": "بنها",
    "35": "بنها",
    "36": "شبرا الخيمة",
    "37": "شبرا الخيمة",
    "38": "شبرا الخيمة",
    "39": "طنطا",
    "41": "طنطا",
    "42": "طنطا",
    "43": "دمنهور",
    "44": "دمنهور",
    "45": "دمنهور",
    "46": "المحلة الكبرى",
    "47": "المحلة الكبرى",
    "48": "المحلة الكبرى",
    "51": "الإسكندرية",
    "52": "الإسكندرية",
    "53": "الإسكندرية",
    "54": "الإسكندرية",
    "55": "الإسكندرية",
    "56": "قنا",
    "57": "قنا",
    "58": "قنا",
    "59": "شمال سيناء",
    "61": "العريش",
    "62": "العريش",
    "63": "العريش",
    "64": "الغردقة",
    "65": "الغردقة",
    "66": "الغردقة",
    "67": "المنيا",
    "68": "المنيا",
    "69": "المنيا",
    "71": "سوهاج - مركز سوهاج",
    "72": "سوهاج",
    "73": "قنا - مركز قنا",
    "74": "أسيوط - مركز أسيوط",
    "75": "بني سويف",
    "76": "الفيوم",
    "77": "بورسعيد",
    "78": "دمياط",
    "79": "الزقازيق",
    "81": "الغردقة",
    "82": "سوهاج",
    "83": "قنا",
    "84": "أسيوط",
    "85": "المنيا",
    "86": "بني سويف",
    "87": "الفيوم",
    "88": "بورسعيد",
    "89": "دمياط",
    "91": "الغردقة",
    "92": "سوهاج",
    "93": "قنا",
    "94": "أسيوط",
    "95": "المنيا",
}

CENTURY_PREFIXES: dict[str, int] = {"2": 1900, "3": 2000}

ID_LENGTH = 14


@dataclass(frozen=True)
class NationalIdInfo:
    """Parsed information extracted from a national ID."""

    national_id: str
    birth_date: date
    century: int
    year: int
    month: int
    day: int
    governorate_code: str
    governorate_name: str
    is_male: bool

    @property
    def gender(self) -> str:
        return "M" if self.is_male else "F"


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_national_id(national_id: str | None) -> NationalIdInfo | None:
    """Parse a national ID, returning ``None`` when it is malformed.

    Use :func:`validate_national_id` when a raised :class:`ValueError` with an
    Arabic message is wanted instead.
    """
    try:
        return _parse_national_id(national_id)
    except ValueError:
        return None


def _parse_national_id(national_id: str | None) -> NationalIdInfo:
    """Parse and validate a national ID.

    Raises:
        ValueError: with an Arabic message when the ID is malformed.
    """
    from app.utils.arabic import to_ascii_digits

    if national_id is None:
        raise ValueError(Messages.NATIONAL_ID_LENGTH)

    value = to_ascii_digits(str(national_id)).strip()
    if len(value) != ID_LENGTH:
        raise ValueError(Messages.NATIONAL_ID_LENGTH)
    if not value.isdigit():
        raise ValueError(Messages.NATIONAL_ID_DIGITS_ONLY)

    century_prefix = value[0]
    if century_prefix not in CENTURY_PREFIXES:
        raise ValueError(Messages.NATIONAL_ID_CENTURY)
    century = CENTURY_PREFIXES[century_prefix]

    yy, mm, dd = int(value[1:3]), int(value[3:5]), int(value[5:7])
    year = century + yy
    parsed_date = _valid_date(year, mm, dd)
    if parsed_date is None:
        raise ValueError(Messages.NATIONAL_ID_DATE_INVALID)

    governorate_code = value[7:9]
    gender_digit = int(value[12])

    return NationalIdInfo(
        national_id=value,
        birth_date=parsed_date,
        century=century,
        year=year,
        month=mm,
        day=dd,
        governorate_code=governorate_code,
        governorate_name=GOVERNORATE_CODES.get(governorate_code, "غير محدد"),
        is_male=gender_digit % 2 == 1,
    )


def is_valid_national_id(national_id: str | None) -> bool:
    """Return True when ``national_id`` is a well-formed national ID."""
    if not national_id:
        return False
    return parse_national_id(national_id) is not None


def validate_national_id(
    national_id: str | None,
    *,
    birth_date: date | None = None,
    gender: str | None = None,
) -> NationalIdInfo | None:
    """Validate an ID together with the person fields it encodes.

    Returns the parsed info, or ``None`` when no ID was supplied.

    Raises:
        ValueError: with an Arabic message on any mismatch.
    """
    if national_id is None or str(national_id).strip() == "":
        return None

    info = _parse_national_id(national_id)

    if gender is not None:
        normalized_gender = gender.strip().upper()
        if normalized_gender not in {"M", "F"}:
            raise ValueError(Messages.GENDER_INVALID)
        if (normalized_gender == "M") != info.is_male:
            raise ValueError(Messages.NATIONAL_ID_GENDER)

    if birth_date is not None and birth_date != info.birth_date:
        raise ValueError(Messages.NATIONAL_ID_MISMATCH_DATE)

    return info


def mask_national_id(national_id: str | None) -> str | None:
    """Mask all but the last four digits: ``29801011234567`` -> ``********4567``."""
    if not national_id:
        return national_id
    if len(national_id) <= 4:
        return "*" * len(national_id)
    return "*" * (len(national_id) - 4) + national_id[-4:]
