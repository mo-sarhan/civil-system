"""Marriage model linking a husband and a wife."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

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


class MarriageStatus(str, Enum):
    """Allowed marriage states."""

    MARRIED = "married"
    DIVORCED = "divorced"
    WIDOWED = "widowed"
    SEPARATED = "separated"


class Marriage(Base):
    """A union between two people.

    ``end_date`` is NULL while the marriage is ongoing.  ``status`` is derived
    automatically by the service layer but is stored so it can be filtered on.
    """

    __tablename__ = "marriage"

    id: Mapped[int] = mapped_column(primary_key=True)
    husband_id: Mapped[int] = mapped_column(
        "husband_id", ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    wife_id: Mapped[int] = mapped_column(
        "wife_id", ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date | None] = mapped_column("start_date", Date)
    end_date: Mapped[date | None] = mapped_column("end_date", Date)
    status: Mapped[str] = mapped_column(
        "status", String(20), nullable=False, default=MarriageStatus.MARRIED.value
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

    husband = relationship("Person", foreign_keys=[husband_id], lazy="select")
    wife = relationship("Person", foreign_keys=[wife_id], lazy="select")

    __table_args__ = (
        CheckConstraint("husband_id <> wife_id", name="ck_marriage_distinct_partners"),
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_marriage_end_after_start",
        ),
        CheckConstraint(
            "status IN ('married','divorced','widowed','separated')",
            name="ck_marriage_status",
        ),
        Index("ix_marriage_husband", "husband_id"),
        Index("ix_marriage_wife", "wife_id"),
        Index(
            "ix_marriage_partner_pair",
            func.least(husband_id, wife_id),
            func.greatest(husband_id, wife_id),
            unique=True,
        ),
    )

    def partner_of(self, person_id: int) -> int:
        """Return the spouse's id for ``person_id``."""
        if person_id == self.husband_id:
            return self.wife_id
        return self.husband_id

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Marriage {self.husband_id}<->{self.wife_id} {self.status}>"
