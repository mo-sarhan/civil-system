"""Arabic text normalisation helpers.

Used for fuzzy search, duplicate detection, parent matching during import and
person-name parsing.  The goal is that two spellings of the same Arabic name
compare equal: ``مُحَمَّد`` == ``محمد``, ``إحمد`` == ``احمد`` == ``آحمد``.
"""

from __future__ import annotations

import re
import unicodedata

#: Arabic diacritics (tashkeel), tatweel and Quranic annotation marks.
#: Ranges are written with explicit escapes because writing them as literal
#: characters is error prone: "U+0610-U+064B" would swallow every Arabic letter.
_TASHKEEL = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")

#: Letter-level folding. Each key maps to its canonical (most common) letter.
_CHAR_FOLD: dict[str, str] = {
    "أ": "ا",
    "إ": "ا",
    "آ": "ا",
    "ٱ": "ا",
    "ٲ": "ا",
    "ٳ": "ا",
    "ة": "ه",
    "ى": "ي",
    "ئ": "ي",
    "ؤ": "و",
    "ﻻ": "لا",
    "ﻵ": "لا",
    "ﻷ": "لا",
}

#: Multi-character sequences folded before single characters.
_SEQUENCE_FOLD: tuple[tuple[str, str], ...] = (
    ("الله", "الله"),  # keep, listed for documentation clarity
)

_TRANSLITERATION: dict[str, str] = {
    "٠": "0",
    "١": "1",
    "٢": "2",
    "٣": "3",
    "٤": "4",
    "٥": "5",
    "٦": "6",
    "٧": "7",
    "٨": "8",
    "٩": "9",
    "۰": "0",
    "۱": "1",
    "۲": "2",
    "۳": "3",
    "۴": "4",
    "۵": "5",
    "۶": "6",
    "۷": "7",
    "۸": "8",
    "۹": "9",
}

_WS = re.compile(r"\s+")
#: Keep ASCII word characters plus the Arabic blocks; everything else
#: becomes a space. Explicit classes (instead of ``\w``) keep this identical to
#: the SQL normaliser, which cannot rely on a Unicode-aware regex engine.
_NON_WORD = re.compile("[^A-Za-z0-9_\u0600-\u06ff]+")


def to_ascii_digits(value: str) -> str:
    """Convert Arabic-Indic / Extended Arabic-Indic digits to ASCII."""
    return "".join(_TRANSLITERATION.get(ch, ch) for ch in value)


def to_arabic_digits(value: str) -> str:
    """Convert ASCII digits to Arabic-Indic digits (٠-٩)."""
    table = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
    return value.translate(table)


def normalize_name(value: str | None) -> str:
    """Return a canonical, searchable form of an Arabic (or Latin) name.

    Steps: convert digits, strip tashkeel/tatweel, unify alef variants and
    ta-marbuta, unify alef-maqsura to ya, drop non-letter characters and
    collapse whitespace.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = to_ascii_digits(text)
    text = _TASHKEEL.sub("", text)
    for src, dst in _CHAR_FOLD.items():
        text = text.replace(src, dst)
    text = _NON_WORD.sub(" ", text)
    text = _WS.sub(" ", text).strip().lower()
    return text


def name_tokens(value: str | None) -> list[str]:
    """Split a normalised name into ordered tokens."""
    normalized = normalize_name(value)
    return normalized.split() if normalized else []


def full_name_key(value: str | None) -> str:
    """Order-insensitive key for matching names regardless of word order."""
    tokens = sorted(name_tokens(value))
    return " ".join(tokens)


def similarity(a: str | None, b: str | None) -> float:
    """Dice coefficient over bigrams - good for Arabic names, 0.0 - 1.0."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    bigrams_a = {na[i : i + 2] for i in range(len(na) - 1)} or {na}
    bigrams_b = {nb[i : i + 2] for i in range(len(nb) - 1)} or {nb}
    intersection = len(bigrams_a & bigrams_b)
    return (2.0 * intersection) / (len(bigrams_a) + len(bigrams_b))


NAME_PART_PATTERNS: tuple[str, ...] = (
    "first_name",
    "father_name",
    "grandfather_name",
    "family_name",
)


#: Words that never stand alone as a name part: they bind to the next token
#: (``عبد الله``, ``أبو بكر``, ``بن سالم``).
_NAME_PARTICLES = frozenset({"عبد", "ابو", "ابن", "بن", "ام"})


def _bare_token(token: str) -> str:
    """Strip articles and orthography so a token can be matched as a particle."""
    word = re.sub(r"[^\u0600-\u06ffA-Za-z]", "", token)
    word = word.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    if word.startswith("ال") and len(word) > 2:
        word = word[2:]
    return word.lower()


def _group_name_units(tokens: list[str]) -> list[str]:
    """Merge name particles with the token that follows them."""
    units: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if index + 1 < len(tokens) and _bare_token(token) in _NAME_PARTICLES:
            units.append(f"{token} {tokens[index + 1]}")
            index += 2
        else:
            units.append(token)
            index += 1
    return units


def parse_full_name(full_name: str | None) -> dict[str, str | None]:
    """Split a full name into its parts.

    Arabic civil-registry names are conventionally ``الاسم الأول اسم الأب اسم
    الجد اسم العائلة``.  The function is conservative: fewer than three units
    only fills ``first_name``/``family_name``, particles such as ``عبد`` stay
    glued to the token that follows them, and no part is ever returned empty.
    """
    display_tokens = [
        t for t in re.split(r"\s+", unicodedata.normalize("NFKC", full_name or "")) if t
    ]
    if not display_tokens:
        return {
            "first_name": None,
            "father_name": None,
            "grandfather_name": None,
            "family_name": None,
        }

    units = _group_name_units(display_tokens)
    blank = {"first_name": None, "father_name": None, "grandfather_name": None, "family_name": None}
    if len(units) == 1:
        return {**blank, "first_name": units[0]}
    if len(units) == 2:
        return {**blank, "first_name": units[0], "family_name": units[1]}
    if len(units) == 3:
        return {**blank, "first_name": units[0], "father_name": units[1], "family_name": units[2]}
    return {
        "first_name": units[0],
        "father_name": units[1],
        "grandfather_name": units[2],
        "family_name": " ".join(units[3:]),
    }
