#!/usr/bin/env python
"""Seed the database: bootstrap admin + the sample civil-registry data.

Usage::

    python -m scripts.seed                 # sample data + admin
    python -m scripts.seed --admin-only    # only create/refresh the admin user
    python -m scripts.seed --file other.sql

The admin password is generated once, printed once, and the account is flagged
``must_change_password`` so it must be rotated at first login.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import generate_password, hash_password
from app.db.session import SessionLocal
from app.models.marriage import Marriage, MarriageStatus
from app.models.person import Person
from app.models.user import Role, User
from app.utils.arabic import normalize_name, parse_full_name

DEFAULT_SAMPLE = Path(__file__).resolve().parents[2] / "sample_civil_registry.sql"

BANNER = """
============================================================
  Civil Registry & Family Tree - database seed
============================================================
"""


def ensure_admin(db: Session) -> str:
    """Create the bootstrap admin if missing; return a message."""
    username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
    existing = db.execute(
        select(User).where(func.lower(User.username) == username.lower())
    ).scalar_one_or_none()

    if existing is not None:
        return (
            f"المستخدم الإداري '{username}' موجود بالفعل "
            f"(الصلاحية: {existing.role}) - لم يتم تغيير كلمة المرور."
        )

    password = generate_password(16)
    admin = User(
        username=username,
        full_name="مدير النظام",
        password_hash=hash_password(password),
        role=Role.ADMIN,
        is_active=True,
        must_change_password=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)

    print("=" * 62)
    print("  تم إنشاء حساب المدير - بيانات الدخول (تظهر مرة واحدة فقط)")
    print("-" * 62)
    print(f"  اسم المستخدم : {username}")
    print(f"  كلمة المرور  : {password}")
    print("-" * 62)
    print("  يجب تغيير كلمة المرور عند أول تسجيل دخول.")
    print("=" * 62)
    return f"تم إنشاء المستخدم الإداري '{username}'"


# --------------------------------------------------------------------------- #
# Sample data
# --------------------------------------------------------------------------- #
_INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+(person|marriage)\s+VALUES\s*(.*?);", re.IGNORECASE | re.DOTALL
)


def split_values(block: str) -> list[list[str | None]]:
    """Split an ``INSERT ... VALUES (...)`` block into rows of raw cells.

    A small scanner is used instead of a regex because cell values may contain
    commas inside single quotes (Arabic names do not, but notes might).
    """
    rows: list[list[str | None]] = []
    row: list[str | None] = []
    cell: list[str] = []
    in_quotes = False
    depth = 0

    for char in block:
        if in_quotes:
            if char == "'":
                in_quotes = False
            else:
                cell.append(char)
            continue
        if char == "'":
            in_quotes = True
            continue
        if char == "(":
            depth += 1
            if depth == 1:
                row, cell = [], []
            continue
        elif char == ")":
            depth -= 1
            if depth == 0:
                row.append("".join(cell).strip() or None)
                rows.append(row)
            continue
        elif char == "," and depth == 1:
            row.append("".join(cell).strip() or None)
            cell = []
            continue
        if depth >= 1:
            cell.append(char)
    return rows


def parse_sample_sql(path: Path) -> tuple[list[dict], list[dict]]:
    """Extract person and marriage rows from ``sample_civil_registry.sql``.

    Handles both the 9-column layout used by the shipped sample
    (id, national_id, full_name, gender, birth, death, place, father, mother) and
    a 12-column layout that also carries name parts and notes.
    """
    sql = path.read_text(encoding="utf-8")
    persons: list[dict] = []
    marriages: list[dict] = []

    for table, block in _INSERT_RE.findall(sql):
        for cells in split_values(block):
            if table == "person" and len(cells) >= 9:
                persons.append(
                    {
                        "id": _as_int(cells[0]) or 0,
                        "national_id": cells[1],
                        "full_name": cells[2] or "",
                        "gender": cells[3],
                        "birth_date": _as_date(cells[4]),
                        "death_date": _as_date(cells[5]),
                        "birth_place": cells[6],
                        "father_id": _as_int(cells[7]),
                        "mother_id": _as_int(cells[8]),
                    }
                )
            elif table == "marriage" and len(cells) >= 5:
                marriages.append(
                    {
                        "id": _as_int(cells[0]) or 0,
                        "husband_id": _as_int(cells[1]) or 0,
                        "wife_id": _as_int(cells[2]) or 0,
                        "start_date": _as_date(cells[3]),
                        "end_date": _as_date(cells[4]),
                    }
                )
    return persons, marriages


def _as_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _as_int(value: str | None) -> int | None:
    return int(value) if value and value.strip().isdigit() else None


def load_sample(db: Session, path: Path) -> tuple[int, int]:
    """Insert the sample people and marriages. Idempotent by national ID."""
    persons, marriages = parse_sample_sql(path)
    if not persons:
        print(f"تحذير: لم يتم العثور على سجلات في {path}")
        return 0, 0

    # Parents first so the FK constraints always hold.
    ordered = sorted(
        persons, key=lambda p: (p["father_id"] is not None or p["mother_id"] is not None, p["id"])
    )

    existing_ids = set(db.execute(select(Person.national_id)).scalars())
    existing_ids = {i for i in existing_ids if i}

    created = 0
    id_map: dict[int, int] = {}

    for row in ordered:
        existing_person = db.execute(
            select(Person).where(Person.national_id == row["national_id"])
        ).scalar_one_or_none()
        if existing_person is not None:
            id_map[row["id"]] = existing_person.id
            continue

        parts = parse_full_name(row["full_name"])
        person = Person(
            national_id=row["national_id"],
            full_name=row["full_name"],
            full_name_normalized=normalize_name(row["full_name"]),
            first_name=parts["first_name"],
            father_name=parts["father_name"],
            grandfather_name=parts["grandfather_name"],
            family_name=parts["family_name"],
            gender=row["gender"],
            birth_date=row["birth_date"],
            death_date=row["death_date"],
            birth_place=row["birth_place"],
        )
        db.add(person)
        db.flush()
        id_map[row["id"]] = person.id
        created += 1

    # Now wire parents (needs a second pass because ids are only known now).
    for row in ordered:
        person = db.get(Person, id_map[row["id"]])
        if row["father_id"] and row["father_id"] in id_map:
            person.father_id = id_map[row["father_id"]]
        if row["mother_id"] and row["mother_id"] in id_map:
            person.mother_id = id_map[row["mother_id"]]

    marriage_count = 0
    for row in marriages:
        husband = id_map.get(row["husband_id"])
        wife = id_map.get(row["wife_id"])
        if not husband or not wife:
            continue
        exists = db.execute(
            select(func.count())
            .select_from(Marriage)
            .where(Marriage.husband_id == husband, Marriage.wife_id == wife)
        ).scalar_one()
        if exists:
            continue
        status = (
            MarriageStatus.WIDOWED.value
            if row["end_date"] and row["husband_id"] == 1
            else MarriageStatus.MARRIED.value
        )
        db.add(
            Marriage(
                husband_id=husband,
                wife_id=wife,
                start_date=row["start_date"],
                end_date=row["end_date"],
                status=status,
            )
        )
        marriage_count += 1

    db.commit()
    return created, marriage_count


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the civil registry database")
    parser.add_argument("--file", type=Path, default=DEFAULT_SAMPLE, help="SQL sample file")
    parser.add_argument("--admin-only", action="store_true", help="skip sample data")
    parser.add_argument("--reset-password", action="store_true", help="rotate the admin password")
    args = parser.parse_args()

    print(BANNER)
    print(
        f"  قاعدة البيانات: {settings.postgres_db}@{settings.postgres_host}:{settings.postgres_port}"
    )
    print(f"  البيئة       : {settings.environment}")
    print("-" * 62)

    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"خطأ: تعذر الاتصال بقاعدة البيانات: {exc}")
        print("تأكد من تشغيل الحاويات (make up) أو من صحة متغيرات البيئة.")
        return 1

    try:
        if args.reset_password:
            username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "admin")
            admin = db.execute(
                select(User).where(func.lower(User.username) == username.lower())
            ).scalar_one_or_none()
            if admin is None:
                print(f"لا يوجد مستخدم '{username}' لتغيير كلمة مروره.")
                return 1
            password = generate_password(16)
            admin.password_hash = hash_password(password)
            admin.must_change_password = True
            db.commit()
            print("=" * 62)
            print(f"  كلمة المرور الجديدة لـ '{username}': {password}")
            print("=" * 62)

        else:
            print(ensure_admin(db))

        if not args.admin_only:
            print("-" * 62)
            created, marriages = load_sample(db, args.file)
            print(f"  تم استيراد {created} شخص جديد و {marriages} تسجيل زواج من {args.file.name}")

            total = db.execute(select(func.count()).select_from(Person)).scalar_one()
            print(f"  إجمالي الأشخاص في قاعدة البيانات: {total}")

        # Index statistics so the planner has real numbers right away.
        db.execute(text("ANALYZE person"))
        db.execute(text("ANALYZE marriage"))
        db.execute(text("ANALYZE users"))
        db.commit()
        print("-" * 62)
        print("  تم تحديث إحصاءات الفهارس (ANALYZE)")
        print(BANNER)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
