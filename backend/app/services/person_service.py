"""Person use-cases: CRUD, validation, search, merging."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import Page, Pagination, years_between
from app.models.audit import AuditAction
from app.models.marriage import Marriage
from app.models.person import Person
from app.schemas.person import (
    PERSON_SORT_FIELDS,
    PersonCreate,
    PersonUpdate,
)
from app.services import audit_service, cycle_service
from app.utils.arabic import normalize_name
from app.utils.messages import Messages
from app.utils.national_id import validate_national_id

logger = logging.getLogger(__name__)


class PersonService:
    """All person-related business logic."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    def get(self, person_id: int) -> Person:
        """Fetch a person or raise :class:`NotFoundError`."""
        person = self.db.get(Person, person_id)
        if person is None:
            raise NotFoundError(Messages.PERSON_NOT_FOUND)
        return person

    def get_or_none(self, person_id: int) -> Person | None:
        return self.db.get(Person, person_id)

    def list_persons(
        self,
        *,
        pagination: Pagination,
        q: str | None = None,
        gender: str | None = None,
        birth_year_from: int | None = None,
        birth_year_to: int | None = None,
        birth_place: str | None = None,
        father_id: int | None = None,
        mother_id: int | None = None,
        has_father: bool | None = None,
        has_mother: bool | None = None,
        has_national_id: bool | None = None,
        alive: bool | None = None,
        national_id: str | None = None,
        sort: str = "full_name",
        direction: str = "asc",
    ) -> Page[Person]:
        """Paginated, filtered person list."""
        stmt = select(Person).where(Person.merged_into_id.is_(None))
        count_stmt = select(func.count()).select_from(stmt.subquery())

        conditions = self._filter_conditions(
            q=q,
            gender=gender,
            birth_year_from=birth_year_from,
            birth_year_to=birth_year_to,
            birth_place=birth_place,
            father_id=father_id,
            mother_id=mother_id,
            has_father=has_father,
            has_mother=has_mother,
            has_national_id=has_national_id,
            alive=alive,
            national_id=national_id,
        )
        if conditions:
            stmt = stmt.where(and_(*conditions))
            count_stmt = stmt.with_only_columns(func.count()).order_by(None)

        sort_column = getattr(Person, PERSON_SORT_FIELDS.get(sort, "full_name"))
        order = sort_column.desc() if direction.lower() == "desc" else sort_column.asc()
        # Secondary sort keeps pagination stable.
        stmt = (
            stmt.order_by(order, Person.id.asc())
            .limit(pagination.page_size)
            .offset(pagination.offset)
        )

        total = self.db.execute(count_stmt).scalar_one()
        items = list(self.db.execute(stmt).scalars().unique())
        return Page.build(items, int(total), pagination.page, pagination.page_size)

    def _filter_conditions(self, **kwargs: Any) -> list[Any]:
        """Translate query parameters into SQLAlchemy predicates."""
        conditions: list[Any] = []

        q = kwargs.get("q")
        if q:
            # The search alternatives must be OR-ed together; the caller ANDs
            # this single condition with the other filters.
            conditions.append(or_(*self._search_predicates(q)))

        gender = kwargs.get("gender")
        if gender:
            conditions.append(Person.gender == gender.upper())

        birth_year_from = kwargs.get("birth_year_from")
        birth_year_to = kwargs.get("birth_year_to")
        if birth_year_from:
            conditions.append(Person.birth_date >= date(birth_year_from, 1, 1))
        if birth_year_to:
            conditions.append(Person.birth_date <= date(birth_year_to, 12, 31))

        birth_place = kwargs.get("birth_place")
        if birth_place:
            # Normalise the stored value with the same SQL function the trigger
            # uses, otherwise a query typed as "القاهره" cannot match.
            normalized_place = normalize_name(birth_place)
            if normalized_place:
                conditions.append(
                    func.normalize_arabic_name(Person.birth_place).like(f"%{normalized_place}%")
                )

        if kwargs.get("father_id"):
            conditions.append(Person.father_id == kwargs["father_id"])
        if kwargs.get("mother_id"):
            conditions.append(Person.mother_id == kwargs["mother_id"])

        has_father = kwargs.get("has_father")
        if has_father is not None:
            conditions.append(
                Person.father_id.isnot(None) if has_father else Person.father_id.is_(None)
            )
        has_mother = kwargs.get("has_mother")
        if has_mother is not None:
            conditions.append(
                Person.mother_id.isnot(None) if has_mother else Person.mother_id.is_(None)
            )

        has_national_id = kwargs.get("has_national_id")
        if has_national_id is not None:
            conditions.append(
                Person.national_id.isnot(None) if has_national_id else Person.national_id.is_(None)
            )

        alive = kwargs.get("alive")
        if alive is not None:
            conditions.append(
                Person.death_date.is_(None) if alive else Person.death_date.isnot(None)
            )

        national_id = kwargs.get("national_id")
        if national_id:
            conditions.append(Person.national_id == str(national_id).strip())

        return conditions

    @staticmethod
    def _search_predicates(q: str) -> list[Any]:
        """Predicates matching a free-text query.

        An all-digit query is treated as a national ID, otherwise the term is
        compared against the normalised name (trigram + prefix + token match).
        """
        from app.utils.arabic import to_ascii_digits

        raw = q.strip()
        digits = to_ascii_digits(raw)
        predicates: list[Any] = []

        if digits and digits.isdigit():
            predicates.append(Person.national_id == digits)

        normalized = normalize_name(raw)
        if normalized:
            escaped = normalized.replace("%", "").replace("_", "")
            predicates.extend(
                [
                    Person.full_name_normalized == normalized,
                    Person.full_name_normalized.like(f"{escaped}%"),
                    Person.full_name_normalized.like(f"% {escaped}%"),
                    Person.full_name_normalized.like(f"%{escaped}%"),
                ]
            )
        return predicates or [Person.full_name_normalized == normalized]

    def search(self, q: str, limit: int = 20) -> list[tuple[Person, float, str]]:
        """Fuzzy search returning ``(person, score, matched_by)`` tuples."""
        from app.utils.arabic import to_ascii_digits

        q = q.strip()
        if not q:
            return []

        digits = to_ascii_digits(q)
        if digits.isdigit() and len(digits) >= 4:
            rows = self.db.execute(
                select(Person)
                .where(Person.merged_into_id.is_(None), Person.national_id.like(f"%{digits}%"))
                .limit(limit)
            ).scalars()
            return [(p, 1.0, "national_id") for p in rows]

        normalized = normalize_name(q)
        if not normalized:
            return []

        # 1) exact normalised match, 2) trigram similarity, 3) prefix match.
        candidates: dict[int, tuple[Person, float, str]] = {}
        exact = self.db.execute(
            select(Person)
            .where(Person.merged_into_id.is_(None), Person.full_name_normalized == normalized)
            .limit(limit)
        ).scalars()
        for p in exact:
            candidates[p.id] = (p, 1.0, "exact")

        remaining = limit - len(candidates)
        if remaining > 0:
            escaped = normalized.replace("%", "").replace("_", "")
            fuzzy = self.db.execute(
                select(
                    Person, func.similarity(Person.full_name_normalized, normalized).label("score")
                )
                .where(
                    Person.merged_into_id.is_(None),
                    Person.full_name_normalized % normalized,
                )
                .order_by(text("score DESC"), Person.id)
                .limit(remaining)
            ).all()
            for p, score in fuzzy:
                candidates.setdefault(p.id, (p, round(float(score or 0.0), 4), "fuzzy"))

        remaining = limit - len(candidates)
        if remaining > 0:
            prefix = self.db.execute(
                select(Person)
                .where(
                    Person.merged_into_id.is_(None),
                    Person.full_name_normalized.like(f"{escaped}%"),
                )
                .order_by(Person.full_name_normalized)
                .limit(remaining)
            ).scalars()
            for p in prefix:
                candidates.setdefault(p.id, (p, 0.9, "prefix"))

        results = sorted(candidates.values(), key=lambda item: (-item[1], item[0].full_name))
        return results[:limit]

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    def create(
        self,
        data: PersonCreate,
        *,
        user_id: int | None = None,
        ip: str | None = None,
    ) -> Person:
        """Validate and insert a new person."""
        self._validate_payload(data)

        national_id = data.validated_national_id()
        if national_id:
            self._ensure_national_id_free(national_id)

        parts = data.parsed_name_parts()
        father, mother = self._load_parents(data.father_id, data.mother_id, None)
        self._validate_parent_genders(father, mother)
        self._validate_parent_age(data.birth_date, father, mother)

        family_name = parts["family_name"]
        if not family_name and father is not None:
            family_name = father.family_name
            parts["grandfather_name"] = parts["grandfather_name"] or father.father_name

        person = Person(
            national_id=national_id,
            full_name=data.full_name,
            full_name_normalized=normalize_name(data.full_name),
            first_name=parts["first_name"],
            father_name=parts["father_name"],
            grandfather_name=parts["grandfather_name"],
            family_name=family_name,
            gender=data.gender,
            birth_date=data.birth_date,
            death_date=data.death_date,
            birth_place=data.birth_place,
            father_id=father.id if father else None,
            mother_id=mother.id if mother else None,
            notes=data.notes,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(person)
        try:
            self.db.flush()
        except Exception as exc:  # DB-level constraint (cycle trigger, etc.)
            self.db.rollback()
            raise self._translate_db_error(exc) from exc

        self._auto_marriage(father, mother)
        audit_service.record(
            self.db,
            action=AuditAction.CREATE,
            user_id=user_id,
            entity="person",
            entity_id=person.id,
            details={"full_name": person.full_name},
            ip=ip,
        )
        self.db.commit()
        self.db.refresh(person)
        return person

    def update(
        self,
        person: Person,
        data: PersonUpdate,
        *,
        user_id: int | None = None,
        ip: str | None = None,
    ) -> Person:
        """Apply a partial update after full validation."""
        before = {
            "full_name": person.full_name,
            "national_id": person.national_id,
            "gender": person.gender,
            "birth_date": person.birth_date,
            "father_id": person.father_id,
            "mother_id": person.mother_id,
        }

        merged: dict[str, Any] = {
            "national_id": data.national_id if data.national_id is not None else person.national_id,
            "full_name": data.full_name or person.full_name,
            "gender": data.gender or person.gender,
            "birth_date": data.birth_date if data.birth_date is not None else person.birth_date,
        }
        validate_national_id(
            merged["national_id"], birth_date=merged["birth_date"], gender=merged["gender"]
        )
        if merged["national_id"] and merged["national_id"] != person.national_id:
            self._ensure_national_id_free(merged["national_id"], exclude_id=person.id)

        father_id = data.father_id if "father_id" in data.model_fields_set else person.father_id
        mother_id = data.mother_id if "mother_id" in data.model_fields_set else person.mother_id

        father, mother = self._load_parents(father_id, mother_id, person.id)
        self._validate_parent_genders(father, mother)
        self._validate_parent_age(merged["birth_date"], father, mother)
        cycle_service.would_create_cycle(self.db, person.id, father_id, mother_id)

        if (
            data.birth_date
            and person.birth_date
            and data.death_date is None
            and person.death_date
            and person.death_date < data.birth_date
        ):
            raise ValidationError(Messages.DEATH_BEFORE_BIRTH)

        for field in (
            "first_name",
            "father_name",
            "grandfather_name",
            "family_name",
            "death_date",
            "birth_place",
            "notes",
        ):
            if field in data.model_fields_set:
                setattr(person, field, getattr(data, field))

        if data.full_name:
            person.full_name = data.full_name
            person.full_name_normalized = normalize_name(data.full_name)
            if not person.first_name or not person.family_name:
                from app.utils.arabic import parse_full_name

                for key, value in parse_full_name(data.full_name).items():
                    if value and not getattr(person, key):
                        setattr(person, key, value)

        if "gender" in data.model_fields_set and data.gender:
            person.gender = data.gender
        if "birth_date" in data.model_fields_set:
            person.birth_date = data.birth_date
        if merged["national_id"] != person.national_id:
            person.national_id = merged["national_id"]
        person.father_id = father_id
        person.mother_id = mother_id
        person.updated_by = user_id

        try:
            self.db.flush()
        except Exception as exc:
            self.db.rollback()
            raise self._translate_db_error(exc) from exc

        audit_service.record(
            self.db,
            action=AuditAction.UPDATE,
            user_id=user_id,
            entity="person",
            entity_id=person.id,
            details={
                "changed": _diff(
                    before,
                    {
                        "full_name": person.full_name,
                        "national_id": person.national_id,
                        "gender": person.gender,
                        "birth_date": person.birth_date,
                        "father_id": person.father_id,
                        "mother_id": person.mother_id,
                    },
                )
            },
            ip=ip,
        )
        self.db.commit()
        self.db.refresh(person)
        return person

    def delete(self, person: Person, *, user_id: int | None = None, ip: str | None = None) -> None:
        """Delete a person; children keep their row and lose the link."""
        snapshot = {"full_name": person.full_name, "national_id": person.national_id}
        person_id = person.id
        self.db.delete(person)
        audit_service.record(
            self.db,
            action=AuditAction.DELETE,
            user_id=user_id,
            entity="person",
            entity_id=person_id,
            details=snapshot,
            ip=ip,
        )
        self.db.commit()

    # ------------------------------------------------------------------ #
    # Validation helpers
    # ------------------------------------------------------------------ #
    def _validate_payload(self, data: PersonCreate) -> None:
        if data.death_date and data.birth_date and data.death_date < data.birth_date:
            raise ValidationError(Messages.DEATH_BEFORE_BIRTH)
        if data.birth_date and data.birth_date > date.today():
            raise ValidationError(Messages.BIRTH_IN_FUTURE)

    def _ensure_national_id_free(self, national_id: str, exclude_id: int | None = None) -> None:
        stmt = select(func.count()).select_from(Person).where(Person.national_id == national_id)
        if exclude_id is not None:
            stmt = stmt.where(Person.id != exclude_id)
        if self.db.execute(stmt).scalar_one():
            raise ConflictError(Messages.NATIONAL_ID_DUPLICATE)

    def _load_parents(
        self, father_id: int | None, mother_id: int | None, person_id: int | None
    ) -> tuple[Person | None, Person | None]:
        if father_id is not None and mother_id is not None and father_id == mother_id:
            raise ValidationError("لا يمكن أن يكون الأب والوالدة نفس الشخص")
        if person_id is not None and (father_id == person_id or mother_id == person_id):
            raise ValidationError(Messages.PARENT_SELF)

        father = self.db.get(Person, father_id) if father_id else None
        mother = self.db.get(Person, mother_id) if mother_id else None
        if father_id and father is None:
            raise ValidationError(f"{Messages.PARENT_NOT_FOUND}: الأب")
        if mother_id and mother is None:
            raise ValidationError(f"{Messages.PARENT_NOT_FOUND}: الأم")
        return father, mother

    @staticmethod
    def _validate_parent_genders(father: Person | None, mother: Person | None) -> None:
        if father is not None and father.gender is not None and father.gender != "M":
            raise ValidationError(Messages.FATHER_MUST_BE_MALE)
        if mother is not None and mother.gender is not None and mother.gender != "F":
            raise ValidationError(Messages.MOTHER_MUST_BE_FEMALE)

    @staticmethod
    def _validate_parent_age(
        child_birth: date | None, father: Person | None, mother: Person | None
    ) -> None:
        if child_birth is None:
            return
        min_age = settings.min_parent_age_years
        for parent, label in ((father, "الأب"), (mother, "الأم")):
            if parent is None or parent.birth_date is None:
                continue
            age = years_between(parent.birth_date, child_birth)
            if age < 0:
                raise ValidationError(Messages.PARENT_DIED_BEFORE_CHILD)
            if age < min_age:
                raise ValidationError(
                    Messages.PARENT_TOO_YOUNG.format(actual=round(age, 1), required=min_age)
                    + f" ({label})"
                )

    def _auto_marriage(self, father: Person | None, mother: Person | None) -> None:
        """Create the parents' marriage row when both parents are known."""
        if father is None or mother is None:
            return
        existing = self.db.execute(
            select(func.count())
            .select_from(Marriage)
            .where(Marriage.husband_id == father.id, Marriage.wife_id == mother.id)
        ).scalar_one()
        if not existing:
            self.db.add(
                Marriage(
                    husband_id=father.id,
                    wife_id=mother.id,
                    status="married",
                )
            )

    @staticmethod
    def _translate_db_error(exc: Exception) -> Exception:
        """Map database constraint violations to Arabic API errors."""
        text_repr = str(exc)
        if "person_cycle_detected" in text_repr:
            return ValidationError(Messages.PARENT_CYCLE)
        if "ck_person_national_id_14_digits" in text_repr:
            return ValidationError(Messages.NATIONAL_ID_LENGTH)
        if "uq_person_national_id" in text_repr:
            return ConflictError(Messages.NATIONAL_ID_DUPLICATE)
        if "ck_person_not_own" in text_repr:
            return ValidationError(Messages.PARENT_SELF)
        if "ck_person_death_after_birth" in text_repr:
            return ValidationError(Messages.DEATH_BEFORE_BIRTH)
        if "ck_person_parents_distinct" in text_repr:
            return ValidationError("لا يمكن أن يكون الأب والوالدة نفس الشخص")
        logger.warning("unhandled database error while saving person: %s", text_repr[:300])
        return ValidationError(f"تعذر حفظ السجل: {text_repr[:200]}")

    # ------------------------------------------------------------------ #
    # Merge / duplicates
    # ------------------------------------------------------------------ #
    def merge(
        self,
        target: Person,
        source: Person,
        *,
        user_id: int | None = None,
        username: str | None = None,
        ip: str | None = None,
    ) -> dict[str, Any]:
        """Merge ``source`` into ``target``, re-pointing every reference."""
        if target.id == source.id:
            raise ValidationError(Messages.SELF_MERGE)
        if source.merged_into_id is not None:
            raise ConflictError(Messages.ALREADY_MERGED)
        if target.merged_into_id is not None:
            raise ConflictError(Messages.MERGE_TARGET_MERGED)

        stats = {
            "children_moved": 0,
            "marriages_moved": 0,
            "national_id_adopted": False,
            "created_by_adopted": False,
        }

        # Children of the source become children of the target (no self-parenting).
        result = self.db.execute(
            update(Person)
            .where(Person.father_id == source.id)
            .values(father_id=target.id, updated_by=user_id)
            .execution_options(synchronize_session=False)
        )
        stats["children_moved"] += result.rowcount or 0
        result = self.db.execute(
            update(Person)
            .where(Person.mother_id == source.id)
            .values(mother_id=target.id, updated_by=user_id)
            .execution_options(synchronize_session=False)
        )
        stats["children_moved"] += result.rowcount or 0

        # Children already linked to the target must not end up with both parents
        # pointing at the same person.
        self.db.execute(
            update(Person)
            .where(Person.father_id == target.id, Person.mother_id == target.id)
            .values(mother_id=None)
            .execution_options(synchronize_session=False)
        )
        self.db.execute(
            update(Person)
            .where(Person.mother_id == target.id, Person.father_id == target.id)
            .values(father_id=None)
            .execution_options(synchronize_session=False)
        )

        # Marriages.
        result = self.db.execute(
            update(Marriage)
            .where(Marriage.husband_id == source.id)
            .values(husband_id=target.id)
            .execution_options(synchronize_session=False)
        )
        stats["marriages_moved"] += result.rowcount or 0
        result = self.db.execute(
            update(Marriage)
            .where(Marriage.wife_id == source.id)
            .values(wife_id=target.id)
            .execution_options(synchronize_session=False)
        )
        stats["marriages_moved"] += result.rowcount or 0

        # Drop marriages that became self-marriages or duplicates.
        self._clean_marriages(target.id, source.id)

        # Fill gaps on the target from the source.
        if not target.national_id and source.national_id:
            self._ensure_national_id_free(source.national_id, exclude_id=target.id)
            target.national_id = source.national_id
            stats["national_id_adopted"] = True
        if not target.birth_date and source.birth_date:
            target.birth_date = source.birth_date
        if not target.birth_place and source.birth_place:
            target.birth_place = source.birth_place
        if not target.family_name and source.family_name:
            target.family_name = source.family_name
        if not target.gender and source.gender:
            target.gender = source.gender
        if target.death_date is None and source.death_date is not None:
            target.death_date = source.death_date
        if not target.father_id and source.father_id and source.father_id != target.id:
            target.father_id = source.father_id
        if not target.mother_id and source.mother_id and source.mother_id != target.id:
            target.mother_id = source.mother_id
        if not target.created_by and source.created_by:
            target.created_by = source.created_by
            stats["created_by_adopted"] = True

        target.updated_by = user_id
        source.merged_into_id = target.id
        source.father_id = None
        source.mother_id = None
        source.national_id = None

        audit_service.record(
            self.db,
            action=AuditAction.MERGE,
            user_id=user_id,
            username=username,
            entity="person",
            entity_id=target.id,
            details={
                "source_id": source.id,
                "source_name": source.full_name,
                "target_name": target.full_name,
                **stats,
            },
            ip=ip,
        )
        self.db.commit()
        return stats

    def _clean_marriages(self, target_id: int, source_id: int) -> None:
        """Remove self/duplicate marriages left behind by a merge."""
        self.db.execute(
            delete(Marriage).where(
                or_(Marriage.husband_id == target_id, Marriage.wife_id == target_id),
                Marriage.husband_id == Marriage.wife_id,
            )
        )
        dupes = self.db.execute(
            select(Marriage.husband_id, Marriage.wife_id, func.count())
            .where(
                or_(
                    Marriage.husband_id.in_([target_id, source_id]),
                    Marriage.wife_id.in_([target_id, source_id]),
                )
            )
            .group_by(Marriage.husband_id, Marriage.wife_id)
            .having(func.count() > 1)
        ).all()
        for husband_id, wife_id, _count in dupes:
            self.db.execute(
                delete(Marriage).where(
                    Marriage.husband_id == husband_id, Marriage.wife_id == wife_id
                )
            )


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """Return only the fields that actually changed."""
    changes: dict[str, list[Any]] = {}
    for key, old in before.items():
        new = after.get(key)
        if old != new:
            changes[key] = [old, new]
    return changes
