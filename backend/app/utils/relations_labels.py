"""Arabic labels for every relationship the system can describe."""

from __future__ import annotations

#: Relation codes are the stable English identifiers stored in responses.
SELF = "self"

# --- direct line -----------------------------------------------------------
CHILD_M = "child_m"
CHILD_F = "child_f"
PARENT_M = "parent_m"
PARENT_F = "parent_f"
GRANDCHILD_M = "grandchild_m"
GRANDCHILD_F = "grandchild_f"
GRANDPARENT_M = "grandparent_m"
GRANDPARENT_F = "grandparent_f"
GREAT_GRANDCHILD_M = "great_grandchild_m"
GREAT_GRANDCHILD_F = "great_grandchild_f"
GREAT_GRANDPARENT_M = "great_grandparent_m"
GREAT_GRANDPARENT_F = "great_grandparent_f"

# --- siblings --------------------------------------------------------------
BROTHER = "brother"
SISTER = "sister"
HALF_BROTHER = "half_brother"
HALF_SISTER = "half_sister"

# --- nephews / nieces ------------------------------------------------------
NEPHEW = "nephew"
NIECE = "niece"
GRAND_NEPHEW = "grand_nephew"
GRAND_NIECE = "grand_niece"
NEPHEW_PATERNAL = "nephew_paternal"
NIECE_PATERNAL = "niece_paternal"
NEPHEW_MATERNAL = "nephew_maternal"
NIECE_MATERNAL = "niece_maternal"
GRAND_NEPHEW_PATERNAL = "grand_nephew_paternal"
GRAND_NIECE_PATERNAL = "grand_niece_paternal"
GRAND_NEPHEW_MATERNAL = "grand_nephew_maternal"
GRAND_NIECE_MATERNAL = "grand_niece_maternal"

# --- uncles / aunts --------------------------------------------------------
UNCLE = "uncle"
AUNT = "aunt"
GRAND_UNCLE = "grand_uncle"
GRAND_AUNT = "grand_aunt"
UNCLE_PATERNAL = "uncle_paternal"
AUNT_PATERNAL = "aunt_paternal"
UNCLE_MATERNAL = "uncle_maternal"
AUNT_MATERNAL = "aunt_maternal"
GRAND_UNCLE_PATERNAL = "grand_uncle_paternal"
GRAND_AUNT_PATERNAL = "grand_aunt_paternal"
GRAND_UNCLE_MATERNAL = "grand_uncle_maternal"
GRAND_AUNT_MATERNAL = "grand_aunt_maternal"

# --- cousins ---------------------------------------------------------------
COUSIN_M = "cousin_m"
COUSIN_F = "cousin_f"
SECOND_COUSIN_M = "second_cousin_m"
SECOND_COUSIN_F = "second_cousin_f"

# --- in-laws ---------------------------------------------------------------
BROTHER_IN_LAW = "brother_in_law"
SISTER_IN_LAW = "sister_in_law"
FATHER_IN_LAW = "father_in_law"
MOTHER_IN_LAW = "mother_in_law"
SON_IN_LAW = "son_in_law"
DAUGHTER_IN_LAW = "daughter_in_law"
UNCLE_IN_LAW = "uncle_in_law"
AUNT_IN_LAW = "aunt_in_law"
COUSIN_IN_LAW = "cousin_in_law"

#: ``code -> Arabic label``.
ARABIC_LABELS: dict[str, str] = {
    SELF: "نفسه",
    CHILD_M: "ابن",
    CHILD_F: "ابنة",
    PARENT_M: "أب",
    PARENT_F: "أم",
    GRANDCHILD_M: "حفيد",
    GRANDCHILD_F: "حفيدة",
    GRANDPARENT_M: "جد",
    GRANDPARENT_F: "جدة",
    GREAT_GRANDCHILD_M: "حفيد من الدرجة الثالثة",
    GREAT_GRANDCHILD_F: "حفيدة من الدرجة الثالثة",
    GREAT_GRANDPARENT_M: "جد من الدرجة الثالثة",
    GREAT_GRANDPARENT_F: "جدة من الدرجة الثالثة",
    BROTHER: "أخ",
    SISTER: "أخت",
    HALF_BROTHER: "أخ من الأب أو الأم",
    HALF_SISTER: "أخت من الأب أو الأم",
    NEPHEW: "ابن أخ أو أخت",
    NIECE: "بنت أخ أو أخت",
    GRAND_NEPHEW: "حفيد الأخ أو الأخت",
    GRAND_NIECE: "حفية الأخ أو الأخت",
    NEPHEW_PATERNAL: "ابن العم",
    NIECE_PATERNAL: "بنت العم",
    NEPHEW_MATERNAL: "ابن الخال",
    NIECE_MATERNAL: "بنت الخالة",
    GRAND_NEPHEW_PATERNAL: "حفيد العم",
    GRAND_NIECE_PATERNAL: "حفية العم",
    GRAND_NEPHEW_MATERNAL: "حفيد الخال",
    GRAND_NIECE_MATERNAL: "حفية الخالة",
    UNCLE: "خال أو عم",
    AUNT: "خالة أو عمة",
    GRAND_UNCLE: "خال أو عم من الدرجة الثانية",
    GRAND_AUNT: "خالة أو عمة من الدرجة الثانية",
    UNCLE_PATERNAL: "عم",
    AUNT_PATERNAL: "عة",
    UNCLE_MATERNAL: "خال",
    AUNT_MATERNAL: "خالة",
    GRAND_UNCLE_PATERNAL: "عم من الدرجة الثانية",
    GRAND_AUNT_PATERNAL: "عة من الدرجة الثانية",
    GRAND_UNCLE_MATERNAL: "خال من الدرجة الثانية",
    GRAND_AUNT_MATERNAL: "خالة من الدرجة الثانية",
    COUSIN_M: "ابن عم",
    COUSIN_F: "بنت عم",
    SECOND_COUSIN_M: "ابن عم من الدرجة الثانية",
    SECOND_COUSIN_F: "بنت عم من الدرجة الثانية",
    BROTHER_IN_LAW: "أخ بالزواج",
    SISTER_IN_LAW: "أخت بالزواج",
    FATHER_IN_LAW: "الحمو / والد الزوجة",
    MOTHER_IN_LAW: "الحمة / والدة الزوجة",
    SON_IN_LAW: "ابن الزوجة",
    DAUGHTER_IN_LAW: "بنت الزوجة",
    UNCLE_IN_LAW: "خال أو عم بالزواج",
    AUNT_IN_LAW: "خالة أو عمة بالزواج",
    COUSIN_IN_LAW: "ابن عم بالزواج",
}

#: Templates used when composing a full sentence such as
#: "محمد هو ابن عم أحمد". The Arabic verb agrees with the subject only.
TEMPLATES: dict[str, str] = {
    "m": "{a} هو {rel} {b}",
    "f": "{a} هي {rel} {b}",
}

#: Feminised/masculined nouns for a subset of labels. Arabic nouns are either
#: masculine or feminine, so a single string per code is enough here.
FEMININE_FORMS: dict[str, str] = {
    CHILD_M: "ابنة",
    GRANDCHILD_M: "حفيدة",
    GREAT_GRANDCHILD_M: "حفيدة من الدرجة الثالثة",
    NEPHEW: "بنت أخ أو أخت",
    GRAND_NEPHEW: "بنت أخ أو أخت من الدرجة الثانية",
    NEPHEW_PATERNAL: "بنت العم",
    NEPHEW_MATERNAL: "بنت الخال",
    UNCLE: "خالة أو عمة",
    GRAND_UNCLE: "خالة أو عمة من الدرجة الثانية",
    UNCLE_PATERNAL: "عة",
    UNCLE_MATERNAL: "خالة",
    COUSIN_M: "بنت عم",
    SECOND_COUSIN_M: "بنت عم من الدرجة الثانية",
    SON_IN_LAW: "بنت الزوجة",
    BROTHER_IN_LAW: "أخت بالزواج",
    UNCLE_IN_LAW: "خالة أو عمة بالزواج",
    COUSIN_IN_LAW: "بنت عم بالزواج",
    PARENT_M: "أم",
    GRANDPARENT_M: "جدة",
    GREAT_GRANDPARENT_M: "جدة من الدرجة الثالثة",
    CHILD_F: "ابن",
    GRANDCHILD_F: "حفيد",
    GREAT_GRANDCHILD_F: "حفيد من الدرجة الثالثة",
}

#: Ordinal wording for deeper generations.
ORDINALS: dict[int, str] = {
    1: "",
    2: "",
    3: "من الدرجة الثالثة",
    4: "من الدرجة الرابعة",
    5: "من الدرجة الخامسة",
}


def label_for(code: str) -> str:
    """Return the Arabic label for a relation code."""
    return ARABIC_LABELS.get(code, "قريب")


def label_for_person(code: str, *, gender: str | None) -> str:
    """Return the Arabic label adjusted for the *target* person's gender."""
    if gender == "F" and code in FEMININE_FORMS:
        return FEMININE_FORMS[code]
    return ARABIC_LABELS.get(code, "قريب")


def uncle_code(degree: int, *, paternal: bool, gender: str | None) -> str:
    """Code for an uncle/aunt ``degree`` steps above the common ancestor.

    ``degree`` is 1 for a father/brother of the parent and 2 for the next
    degree up. ``paternal`` says whether the branch below the common ancestor
    hangs from the father's side, which Arabic distinguishes strictly
    (عم / عة) versus (خال / خالة).
    """
    if degree <= 1:
        if paternal:
            return UNCLE_PATERNAL if gender == "M" else AUNT_PATERNAL
        return UNCLE_MATERNAL if gender == "M" else AUNT_MATERNAL
    if paternal:
        return GRAND_UNCLE_PATERNAL if gender == "M" else GRAND_AUNT_PATERNAL
    return GRAND_UNCLE_MATERNAL if gender == "M" else GRAND_AUNT_MATERNAL


def nephew_code(degree: int, *, paternal: bool, gender: str | None) -> str:
    """Code for the nephew/niece on the other side of the common ancestor."""
    if degree <= 1:
        if paternal:
            return NEPHEW_PATERNAL if gender == "M" else NIECE_PATERNAL
        return NEPHEW_MATERNAL if gender == "M" else NIECE_MATERNAL
    if paternal:
        return GRAND_NEPHEW_PATERNAL if gender == "M" else GRAND_NIECE_PATERNAL
    return GRAND_NEPHEW_MATERNAL if gender == "M" else GRAND_NIECE_MATERNAL


def _degree_free(label: str) -> str:
    """Drop the embedded degree suffix so ``generation_ordinal`` can add it."""
    return label.split(" من ", 1)[0]


LINEAL_ANCESTORS: dict[int, dict[str, str]] = {
    1: {"M": PARENT_M, "F": PARENT_F},
    2: {"M": GRANDPARENT_M, "F": GRANDPARENT_F},
    3: {"M": GREAT_GRANDPARENT_M, "F": GREAT_GRANDPARENT_F},
}

LINEAL_DESCENDANTS: dict[int, dict[str, str]] = {
    1: {"M": CHILD_M, "F": CHILD_F},
    2: {"M": GRANDCHILD_M, "F": GRANDCHILD_F},
    3: {"M": GREAT_GRANDCHILD_M, "F": GREAT_GRANDCHILD_F},
}


def lineal_ancestor_label(generation: int, gender: str | None) -> str:
    """Arabic label for an ancestor ``generation`` steps above the subject.

    ``generation`` is 1 for a parent, 2 for a grandparent, and so on. The
    gender belongs to the ancestor, so a female ancestor is always labelled
    with the feminine word (أم / جدة).
    """
    codes = LINEAL_ANCESTORS.get(generation, LINEAL_ANCESTORS[3])
    code = codes["F" if gender == "F" else "M"]
    base = _degree_free(ARABIC_LABELS[code])
    return f"{base} {generation_ordinal(generation)}".strip()


def lineal_descendant_label(generation: int, gender: str | None) -> str:
    """Arabic label for a descendant ``generation`` steps below the subject."""
    codes = LINEAL_DESCENDANTS.get(generation, LINEAL_DESCENDANTS[3])
    code = codes["F" if gender == "F" else "M"]
    base = _degree_free(ARABIC_LABELS[code])
    return f"{base} {generation_ordinal(generation)}".strip()


def generation_ordinal(generation: int) -> str:
    """Wording for an ancestor/descendant generation distance."""
    return ORDINALS.get(generation, f"من الدرجة {generation + 1}")


def relation_sentence(a_name: str, a_gender: str | None, rel: str, b_name: str) -> str:
    """Compose a full Arabic sentence describing the relationship."""
    template = TEMPLATES["f" if a_gender == "F" else "m"]
    return template.format(a=a_name, rel=rel, b=b_name)
