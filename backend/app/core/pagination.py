"""Small shared helpers: pagination, dates, masking."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

from app.core.exceptions import ValidationError
from app.utils.messages import Messages

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Envelope returned by every paginated list endpoint."""

    items: list[T]
    total: int = Field(..., description="إجمالي عدد السجلات المطابقة")
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> Page[T]:
        pages = math.ceil(total / page_size) if page_size else 0
        return cls(items=items, total=total, page=page, page_size=page_size, pages=pages)


@dataclass(frozen=True)
class Pagination:
    """Validated pagination parameters."""

    page: int
    page_size: int
    offset: int

    @classmethod
    def from_query(
        cls, page: int = 1, page_size: int | None = None, max_page_size: int = 200
    ) -> Pagination:
        from app.core.config import settings

        size = page_size or settings.default_page_size
        if page < 1:
            raise ValidationError("رقم الصفحة يجب أن يكون 1 أو أكبر")
        if size < 1 or size > max_page_size:
            raise ValidationError(f"حجم الصفحة يجب أن يكون بين 1 و {max_page_size}")
        return cls(page=page, page_size=size, offset=(page - 1) * size)


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""
    return datetime.now(UTC)


def as_date(value: Any) -> date | None:
    """Coerce many date-ish inputs into a ``date``."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    from app.utils.arabic import to_ascii_digits

    text = to_ascii_digits(text)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_date_or_error(value: Any, field_name: str) -> date | None:
    """Like :func:`as_date` but raises an Arabic validation error."""
    try:
        return as_date(value)
    except Exception as exc:  # pragma: no cover - defensive
        raise ValidationError(f"قيمة غير صحيحة للحقل {field_name}") from exc


def years_between(earlier: date, later: date) -> float:
    """Approximate age in years between two dates."""
    return (later - earlier).days / 365.2425


def validate_export_limit(count: int, limit: int = 200_000) -> None:
    """Guard against exporting the whole 1M-row database at once."""
    if count > limit:
        raise ValidationError(Messages.EXPORT_TOO_LARGE)
