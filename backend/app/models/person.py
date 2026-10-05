"""Person model: the core civil-registry record."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Person(Base):
    """A single human being in the civil registry.

    ``full_name_normalized`` is a denormalised copy of ``full_name`` produced by
    :func:`app.utils.arabic.normalize_name`.  It is what the trigram index and
    all fuzzy search predicates use, which keeps Arabic matching index-only.
    """

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: Egyptian national ID, exactly 14 digits. Nullable for old records.
    national_id: Mapped[str | None] = mapped_column(
        "national_id", String(14), nullable=True, unique=True
    )

    full_name: Mapped[str] = mapped_column("full_name", Text, nullable=False)
    full_name_normalized: Mapped[str] = mapped_column(
        "full_name_normalized", Text, nullable=False, server_default=""
    )
    first_name: Mapped[str | None] = mapped_column("first_name", String(100))
    father_name: Mapped[str | None] = mapped_column("father_name", String(100))
    grandfather_name: Mapped[str | None] = mapped_column("grandfather_name", String(100))
    family_name: Mapped[str | None] = mapped_column("family_name", String(100))

    gender: Mapped[str | None] = mapped_column("gender", String(1))
    birth_date: Mapped[date | None] = mapped_column("birth_date", Date)
    death_date: Mapped[date | None] = mapped_column("death_date", Date)
    birth_place: Mapped[str | None] = mapped_column("birth_place", String(255))

    father_id: Mapped[int | None] = mapped_column(
        "father_id", ForeignKey("person.id", ondelete="SET NULL"), index=True
    )
    mother_id: Mapped[int | None] = mapped_column(
        "mother_id", ForeignKey("person.id", ondelete="SET NULL"), index=True
    )

    notes: Mapped[str | None] = mapped_column("notes", Text)
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    created_by: Mapped[int | None] = mapped_column(
        "created_by", ForeignKey("users.id", ondelete="SET NULL")
    )
    updated_by: Mapped[int | None] = mapped_column(
        "updated_by", ForeignKey("users.id", ondelete="SET NULL")
    )
    merged_into_id: Mapped[int | None] = mapped_column(
        "merged_into_id", ForeignKey("person.id", ondelete="SET NULL"), index=True
    )

    father = relationship(
        "Person", remote_side="Person.id", foreign_keys=[father_id], lazy="select"
    )
    mother = relationship(
        "Person", remote_side="Person.id", foreign_keys=[mother_id], lazy="select"
    )

    __table_args__ = (
        CheckConstraint(
            "national_id IS NULL OR national_id ~ '^[0-9]{14}$'",
            name="ck_person_national_id_14_digits",
        ),
        CheckConstraint("gender IS NULL OR gender IN ('M','F')", name="ck_person_gender"),
        CheckConstraint(
            "death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date",
            name="ck_person_death_after_birth",
        ),
        CheckConstraint("father_id IS NULL OR father_id <> id", name="ck_person_not_own_father"),
        CheckConstraint("mother_id IS NULL OR mother_id <> id", name="ck_person_not_own_mother"),
        CheckConstraint(
            "father_id IS NULL OR mother_id IS NULL OR father_id <> mother_id",
            name="ck_person_parents_distinct",
        ),
        CheckConstraint(
            "father_id IS NULL OR mother_id IS NULL OR (id IS NOT NULL AND id <> merged_into_id)",
            name="ck_person_not_self_merged",
        ),
        Index("ix_person_birth_date", "birth_date"),
        Index("ix_person_birth_year", func.date_part("year", birth_date)),
        Index(
            "ix_person_full_name_trgm",
            "full_name_normalized",
            postgresql_using="gin",
            postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
        ),
        Index("ix_person_family_name", "family_name"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Person id={self.id} name={self.full_name!r}>"
