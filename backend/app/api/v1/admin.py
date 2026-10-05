"""Audit-log browser (admin only)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.api.deps import AdminUser, DbSession
from app.models.audit import AuditAction, AuditLog
from app.models.user import User

router = APIRouter(tags=["التدقيق"])


@router.get("/audit-log", response_model=dict, summary="استعراض سجل التدقيق")
def list_audit(
    db: DbSession,
    _admin: AdminUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    action: str | None = None,
    entity: str | None = None,
    entity_id: int | None = None,
    user_id: int | None = None,
    username: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict[str, Any]:
    """Filtered, paginated audit trail."""
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)

    conditions = []
    if action:
        conditions.append(AuditLog.action == action.upper())
    if entity:
        conditions.append(AuditLog.entity == entity)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if user_id:
        conditions.append(AuditLog.user_id == user_id)
    if username:
        conditions.append(AuditLog.username.ilike(f"%{username}%"))
    if date_from:
        conditions.append(AuditLog.created_at >= date_from)
    if date_to:
        conditions.append(AuditLog.created_at <= date_to)

    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.execute(count_stmt).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )

    return {
        "items": [
            {
                "id": r.id,
                "user_id": r.user_id,
                "username": r.username,
                "action": r.action,
                "entity": r.entity,
                "entity_id": r.entity_id,
                "details": r.details,
                "ip": r.ip,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/audit-log/actions", response_model=dict, summary="أنواع العمليات المتاحة")
def actions(_db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Enum values used to populate the filter dropdown."""
    return {
        "actions": [a.value for a in AuditAction],
        "entities": [
            "person",
            "marriage",
            "user",
            "import_job",
            "duplicates",
            "person_relationship",
        ],
    }


@router.get("/audit-log/export", response_model=dict, summary="ملخص سجل التدقيق")
def audit_summary(db: DbSession, _admin: AdminUser) -> dict[str, Any]:
    """Counters grouped by action - rendered as a small chart."""
    rows = db.execute(
        select(AuditLog.action, func.count())
        .group_by(AuditLog.action)
        .order_by(func.count().desc())
    ).all()
    users = db.execute(
        select(User.username, func.count())
        .join(AuditLog, AuditLog.user_id == User.id)
        .group_by(User.username)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    recent = db.execute(select(func.max(AuditLog.created_at))).scalar_one()
    return {
        "by_action": [{"action": r[0], "count": int(r[1])} for r in rows],
        "top_users": [{"username": r[0], "count": int(r[1])} for r in users],
        "latest": recent,
        "total": int(db.execute(select(func.count()).select_from(AuditLog)).scalar_one()),
    }


def count_for(db: Session, **filters: Any) -> int:  # pragma: no cover - helper
    stmt = select(func.count()).select_from(AuditLog)
    conditions = [AuditLog.action == filters["action"]] if "action" in filters else []
    if conditions:
        stmt = stmt.where(and_(*conditions))
    return int(db.execute(stmt).scalar_one())
