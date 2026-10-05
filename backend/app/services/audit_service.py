"""Audit-log writer.

Audit writes must never break the business operation they describe, so all
errors are swallowed and logged.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.audit import AuditAction, AuditLog
from app.models.user import User

logger = get_logger(__name__)


def _resolve_username(db: Session, user_id: int) -> str | None:
    """Look the username up for an audit row that did not carry one."""
    try:
        return db.execute(select(User.username).where(User.id == user_id)).scalar_one_or_none()
    except Exception:  # pragma: no cover - never break the audited operation
        logger.debug("could not resolve username for audit user_id=%s", user_id)
        return None


def record(
    db: Session,
    *,
    action: AuditAction | str,
    user_id: int | None = None,
    username: str | None = None,
    entity: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    commit: bool = False,
) -> AuditLog | None:
    """Append one audit row.

    The row is flushed so it gets an ``id`` but is only committed when
    ``commit=True`` or when the caller commits later.

    ``username`` is denormalised onto the row, and resolved from ``user_id``
    when a call site does not pass it, so the trail stays readable even after
    the account is renamed or deleted.
    """
    if username is None and user_id is not None:
        username = _resolve_username(db, user_id)
    entry = AuditLog(
        user_id=user_id,
        username=username,
        action=action.value if isinstance(action, AuditAction) else str(action),
        entity=entity,
        entity_id=entity_id,
        details=details,
        ip=ip,
    )
    try:
        db.add(entry)
        db.flush()
        if commit:
            db.commit()
    except Exception:  # pragma: no cover - auditing must not break requests
        db.rollback()
        logger.exception("failed to write audit log entry action=%s entity=%s", action, entity)
        return None
    return entry
