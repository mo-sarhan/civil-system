#!/usr/bin/env python
"""Generate a large, realistic family dataset for local development.

Appends after the current maximum ``person.id`` so it can never collide with
existing rows, and every person receives a valid Egyptian national ID derived
from their birth date, gender and governorate.

Recommended run against the compose stack::

    docker compose build backend
    docker compose exec -T backend python -m scripts.seed_bulk --households 5000

Family model per household::

    founder (M) + founder wife (F)     -> married couple, 2-4 children
    each son/daughter may marry        -> in-married spouse (no parents in DB)
    married couples have 0-3 children  -> grandchildren, linked to two parents

``--seed`` keeps the dataset reproducible; ``--db-url`` can point the script at
any Postgres (defaults to the application settings env).
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import insert as insert_stmt  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.base import import_all_models  # noqa: E402
from app.models.marriage import Marriage  # noqa: E402
from app.models.person import Person  # noqa: E402

import_all_models()

MALE_NAMES = [
    "أحمد", "محمد", "محمود", "عمر", "يوسف", "خالد", "حسن", "علي", "إبراهيم",
    "عبد الله", "طارق", "سامي", "هشام", "عمرو", "كريم", "زياد", "عبد الرحمن",
    "حسام", "مصطفى", "عادل", "ماهر", "وائل", "خليل", "رمضان", "حران",
]

FEMALE_NAMES = [
    "فاطمة", "خديجة", "عائشة", "زينب", "منى", "هدى", "ياسمين", "نور", "دعاء",
    "سعاد", "مريم", "أسماء", "عمر", "هادي", "سلمى", "رانيا", "ريم", "نهى",
    "أمنية", "شيماء", "إيمان", "مروة", "غادة", "رشا", "نادية",
]

FAMILY_NAMES = [
    "السيد", "أحمد", "حسن", "محمود", "عبد الله", "النجار", "متولي", "كامل",
    "عبد الحميد", "الشاذلي", "أبو زيد", "الجندي", "فؤاد", "رمضان", "سعد",
    "خليل", "إبراهيم", "عوض", "منصور", "الخطيب", "حسين", "علي", "صالح",
    "نصر", "فرج", "الشعراوي", "الحلواني", "السراج", "العزازي", "الهواري",
]

#: (governorate code, readable name). Codes are real Egyptian ID positions.
REGIONS = [
    ("01", "القاهرة"),
    ("02", "القاهرة"),
    ("51", "الإسكندرية"),
    ("52", "الإسكندرية"),
    ("21", "الفيوم"),
    ("22", "الفيوم"),
    ("17", "بني سويف"),
    ("56", "قنا"),
    ("57", "قنا"),
    ("13", "أسيوط"),
    ("14", "أسيوط"),
    ("11", "سوهاج"),
    ("67", "المنيا"),
    ("68", "المنيا"),
    ("27", "دمياط"),
    ("24", "بورسعيد"),
    ("30", "الزقازيق"),
    ("64", "الغردقة"),
]

#: Roughly: mothers are a little younger on average than fathers.
WIFE_AGE_OFFSET = (-4, 3)


def _shift_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb edge-case in a leap year
        return d.replace(month=3, day=1)


class BulkGenerator:
    """In-memory model of the dataset; ids are assigned in creation order."""

    def __init__(
        self,
        rng: random.Random,
        base_person_id: int,
        base_marriage_id: int,
        used_national_ids: set[str] | None = None,
    ) -> None:
        self.rng = rng
        self.next_person_id = base_person_id
        self.next_marriage_id = base_marriage_id
        self.persons: list[dict] = []
        self.marriages: list[dict] = []
        self._serial = 0
        self._used_national_ids: set[str] = set(used_national_ids or ())

    # -- helpers ---------------------------------------------------------
    def add_person(
        self,
        *,
        first: str,
        father_name: str,
        grandfather_name: str,
        family_name: str,
        gender: str,
        birth_date: date,
        birth_place: str,
        gov: str,
        death_date: date | None = None,
        father_id: int | None = None,
        mother_id: int | None = None,
    ) -> dict:
        row = {
            "id": self.next_person_id,
            "national_id": self._national_id(gender, birth_date, gov),
            "full_name": f"{first} {father_name} {grandfather_name} {family_name}",
            "first_name": first,
            "father_name": father_name,
            "grandfather_name": grandfather_name,
            "family_name": family_name,
            "gender": gender,
            "birth_date": birth_date,
            "death_date": death_date,
            "birth_place": birth_place,
            "father_id": father_id,
            "mother_id": mother_id,
        }
        self.persons.append(row)
        self.next_person_id += 1
        return row

    def add_marriage(
        self,
        husband: dict,
        wife: dict,
        start_date: date | None,
        end_date: date | None = None,
        status: str = "married",
    ) -> dict:
        row = {
            "id": self.next_marriage_id,
            "husband_id": husband["id"],
            "wife_id": wife["id"],
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
        }
        self.marriages.append(row)
        self.next_marriage_id += 1
        return row

    def _national_id(self, gender: str, birth_date: date, gov: str) -> str:
        """A structurally valid Egyptian national ID, unique by construction."""
        year = birth_date.year
        century = "2" if year < 2000 else "3"
        core = f"{century}{year % 100:02d}{birth_date.month:02d}{birth_date.day:02d}{gov}"
        while True:
            serial = f"{self._serial % 1000:03d}"
            self._serial += 1
            candidate = f"{core}{serial}{1 if gender == 'M' else 2}0"
            if candidate not in self._used_national_ids:
                self._used_national_ids.add(candidate)
                return candidate

    def _birth(self, lo_year: int, hi_year: int) -> date:
        return date(self.rng.randint(lo_year, hi_year), self.rng.randint(1, 12), self.rng.randint(1, 28))


def _random_name(rng: random.Random, gender: str, used: set[str]) -> str:
    pool = MALE_NAMES if gender == "M" else FEMALE_NAMES
    for _ in range(20):
        name = rng.choice(pool)
        if name not in used:
            used.add(name)
            return name
    return rng.choice(pool)


def _death_date(rng: random.Random, birth: date) -> date | None:
    """Deceased people get a plausible death date up to 2020."""
    years = rng.randint(55, 85)
    death = _shift_years(birth, years)
    if death.year > 2020:
        death = date(2019, rng.randint(1, 12), rng.randint(1, 28))
    return death


def build_household(gen: BulkGenerator, household_index: int) -> None:
    rng = gen.rng
    gov, place = rng.choice(REGIONS)
    family = rng.choice(FAMILY_NAMES)

    # --- The founder couple ---------------------------------------------
    founder_y = rng.randint(1940, 1962)
    founder = gen.add_person(
        first=_random_name(rng, "M", set()),
        father_name=_random_name(rng, "M", set()),
        grandfather_name=_random_name(rng, "M", set()),
        family_name=family,
        gender="M",
        birth_date=gen._birth(founder_y, founder_y + 2),
        birth_place=place,
        gov=gov,
        death_date=_death_date(rng, gen._birth(founder_y, founder_y + 2)) if rng.random() < 0.35 else None,
    )
    wife_y = max(founder_y + WIFE_AGE_OFFSET[0], 1940)
    wife_y = min(wife_y + WIFE_AGE_OFFSET[1], 1968)
    wife = gen.add_person(
        first=_random_name(rng, "F", set()),
        father_name=_random_name(rng, "M", set()),
        grandfather_name=_random_name(rng, "M", set()),
        family_name=rng.choice(FAMILY_NAMES),
        gender="F",
        birth_date=gen._birth(wife_y, wife_y + 2),
        birth_place=place,
        gov=gov,
        death_date=_death_date(rng, gen._birth(wife_y, wife_y + 2)) if rng.random() < 0.30 else None,
    )

    couple_status = "married"
    if founder["death_date"] is not None or wife["death_date"] is not None:
        couple_status = "widowed"
    gen.add_marriage(
        founder,
        wife,
        start_date=_shift_years(wife["birth_date"], rng.randint(18, 23)),
        end_date=founder["death_date"] or wife["death_date"] if couple_status == "widowed" else None,
        status=couple_status,
    )

    # --- Children (only the founder couple's own descendants) ------------
    children: list[tuple[dict, str]] = []
    n_children = rng.randint(2, 4)
    for i in range(n_children):
        child_gender = rng.choice("MF")
        child_y = min(founder["birth_date"].year + 22 + i * 3 + rng.randint(-2, 2), 1996)
        child = gen.add_person(
            first=_random_name(rng, child_gender, set()),
            father_name=founder["first_name"],
            grandfather_name=founder["father_name"],
            family_name=family,
            gender=child_gender,
            birth_date=gen._birth(child_y, child_y + 1),
            birth_place=place,
            gov=gov,
            father_id=founder["id"],
            mother_id=wife["id"],
            death_date=_shift_years(gen._birth(child_y, child_y + 1), 35) if rng.random() < 0.04 else None,
        )
        children.append((child, child_gender))

    # --- Marry those children and add grandchildren ----------------------
    for child, child_gender in children:
        if rng.random() > 0.8:
            continue
        spouse_gender = "F" if child_gender == "M" else "M"
        spouse_y = max(child["birth_date"].year + rng.randint(-3, 3), 1960)
        spouse = gen.add_person(
            first=_random_name(rng, spouse_gender, set()),
            father_name=_random_name(rng, "M", set()),
            grandfather_name=_random_name(rng, "M", set()),
            family_name=rng.choice(FAMILY_NAMES),
            gender=spouse_gender,
            birth_date=gen._birth(spouse_y, spouse_y + 1),
            birth_place=rng.choice(REGIONS)[1],
            gov=rng.choice(REGIONS)[0],
        )
        husband, wife_of_mar = (child, spouse) if child_gender == "M" else (spouse, child)
        start = _shift_years(min(husband["birth_date"], wife_of_mar["birth_date"]), rng.randint(20, 26))
        status = "married"
        end_date = None
        if rng.random() < 0.05:
            status = "divorced"
            end_date = _shift_years(start, rng.randint(3, 15))
        elif rng.random() < 0.02:
            status = "widowed"
        gen.add_marriage(husband, wife_of_mar, start_date=start, end_date=end_date, status=status)

        n_grandchildren = rng.randint(0, 3)
        for _ in range(n_grandchildren):
            gc_gender = rng.choice("MF")
            father = child if child_gender == "M" else spouse
            mother = spouse if child_gender == "M" else child
            gc_y = min(father["birth_date"].year + rng.randint(21, 31), 2024)
            gen.add_person(
                first=_random_name(rng, gc_gender, set()),
                father_name=father["first_name"],
                grandfather_name=(
                    founder["first_name"] if child_gender == "M" else spouse["father_name"]
                ),
                family_name=father["family_name"],
                gender=gc_gender,
                birth_date=gen._birth(gc_y, gc_y),
                birth_place=rng.choice(REGIONS)[1],
                gov=rng.choice(REGIONS)[0],
                father_id=father["id"],
                mother_id=mother["id"],
            )


def _chunks(rows: list[dict], size: int):
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--households", type=int, default=5000, help="عدد الأسر المولَّدة")
    parser.add_argument("--seed", type=int, default=7, help="بذرة التوليد (تكرارية)")
    parser.add_argument("--batch", type=int, default=2000, help="حجم دفعة الإدراج")
    parser.add_argument(
        "--db-url",
        default=None,
        help="DATABASE_URL اختياري (بشكل افتراضي يُستخدم إعدادات التطبيق)",
    )
    args = parser.parse_args()

    if args.db_url:
        os.environ["DATABASE_URL"] = args.db_url

    from app.db.session import SessionLocal  # noqa: PLC0415

    db = SessionLocal()
    try:
        base_person_id = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM person")).scalar() or 0
        base_marriage_id = db.execute(text("SELECT COALESCE(MAX(id), 0) FROM marriage")).scalar() or 0
        existing_ids = {
            row[0]
            for row in db.execute(
                text("SELECT national_id FROM person WHERE national_id IS NOT NULL")
            ).all()
        }

        rng = random.Random(args.seed)
        gen = BulkGenerator(rng, base_person_id + 1, base_marriage_id + 1, existing_ids)
        for household in range(args.households):
            build_household(gen, household)
            if (household + 1) % 1000 == 0:
                print(f"  ... {household + 1} أسر ({len(gen.persons)} شخص)")

        for chunk in _chunks(gen.persons, args.batch):
            db.execute(insert_stmt(Person), chunk)
        for chunk in _chunks(gen.marriages, args.batch):
            db.execute(insert_stmt(Marriage), chunk)

        db.execute(
            text("SELECT setval(pg_get_serial_sequence('person', 'id'), GREATEST(COALESCE(MAX(id), 1), 1)) FROM person")
        )
        db.execute(
            text("SELECT setval(pg_get_serial_sequence('marriage', 'id'), GREATEST(COALESCE(MAX(id), 1), 1)) FROM marriage")
        )
        db.commit()

        print("=" * 60)
        print("  تم التوليد بنجاح")
        print("-" * 60)
        print(f"  الأسر          : {args.households}")
        print(f"  الأشخاص       : {len(gen.persons):,} (أول معرّف {base_person_id + 1})")
        print(f"  الزيجات       : {len(gen.marriages):,} (أول معرّف {base_marriage_id + 1})")
        print(f"  بذرة          : {args.seed}")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()