"""SQLAlchemy declarative base and model registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import DeclarativeBase

if TYPE_CHECKING:  # pragma: no cover
    pass


class Base(DeclarativeBase):
    """Base class for every ORM model."""


def import_all_models() -> None:
    """Import all model modules so Alembic autogenerate sees them."""
    from app.models import (  # noqa: F401
        audit,
        import_job,
        marriage,
        person,
        user,
    )


__all__ = ["Base", "import_all_models"]
