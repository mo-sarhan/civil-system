"""Audit trail for every read and write of personal data."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditAction(str, Enum):
    """Auditable actions."""

    VIEW = "VIEW"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    MERGE = "MERGE"
    SEARCH = "SEARCH"


class AuditLog(Base):
    """One immutable audit row."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        "user_id", ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    username: Mapped[str | None] = mapped_column("username", String(80))
    action: Mapped[str] = mapped_column("action", String(20), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column("entity", String(50), index=True)
    entity_id: Mapped[int | None] = mapped_column("entity_id", Integer)
    details: Mapped[dict | None] = mapped_column("details", JSONB)
    ip: Mapped[str | None] = mapped_column("ip", String(64))
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_audit_entity_created", "entity", "created_at"),
        Index("ix_audit_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<AuditLog {self.action} {self.entity}:{self.entity_id}>"
