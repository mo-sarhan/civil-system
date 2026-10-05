"""Application user and role definitions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Role:
    """Role name constants (also used for dependency checks)."""

    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"

    ALL = (ADMIN, EDITOR, VIEWER)
    #: Roles allowed to read/write, ordered from most to least privileged.
    HIERARCHY = (ADMIN, EDITOR, VIEWER)


ROLE_LABELS_AR: dict[str, str] = {
    Role.ADMIN: "مدير النظام",
    Role.EDITOR: "محرر",
    Role.VIEWER: "مستخدم للعرض فقط",
}


class User(Base):
    """A login able to use the system."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column("username", String(80), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column("full_name", String(150))
    password_hash: Mapped[str] = mapped_column("password_hash", String(255), nullable=False)
    role: Mapped[str] = mapped_column("role", String(20), nullable=False, default=Role.VIEWER)
    is_active: Mapped[bool] = mapped_column("is_active", Boolean, nullable=False, default=True)
    must_change_password: Mapped[bool] = mapped_column(
        "must_change_password", Boolean, nullable=False, default=False
    )
    failed_login_count: Mapped[int] = mapped_column("failed_login_count", default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column("locked_until", DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column("last_login_at", DateTime(timezone=True))
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

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User {self.username} role={self.role}>"
