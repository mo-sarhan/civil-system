"""Marriage endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AdminUser, DbSession, ReaderUser, WriterUser, get_client_ip
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.audit import AuditAction
from app.models.marriage import Marriage
from app.models.person import Person
from app.schemas.marriage import (
    MarriageCreate,
    MarriageDeleteResult,
    MarriageOut,
    MarriageUpdate,
)
from app.services import audit_service
from app.utils.messages import Messages

router = APIRouter(prefix="/marriages", tags=["الزواج"])


def _to_out(db: Session, marriage: Marriage) -> MarriageOut:
    husband = db.get(Person, marriage.husband_id)
    wife = db.get(Person, marriage.wife_id)
    return MarriageOut(
        id=marriage.id,
        husband_id=marriage.husband_id,
        wife_id=marriage.wife_id,
        start_date=marriage.start_date,
        end_date=marriage.end_date,
        status=marriage.status,
        notes=marriage.notes,
        created_at=marriage.created_at,
        updated_at=marriage.updated_at,
        husband_name=husband.full_name if husband else None,
        wife_name=wife.full_name if wife else None,
    )


@router.get("", response_model=dict, summary="قائمة سجلات الزواج")
def list_marriages(
    db: DbSession,
    user: ReaderUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    person_id: int | None = Query(default=None, description="تصفية حسب أحد الطرفين"),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    stmt = select(Marriage)
    count_stmt = select(func.count()).select_from(Marriage)
    conditions = []
    if person_id is not None:
        conditions.append((Marriage.husband_id == person_id) | (Marriage.wife_id == person_id))
    if status_filter:
        conditions.append(Marriage.status == status_filter)
    for condition in conditions:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    total = db.execute(count_stmt).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Marriage.id.desc()).limit(page_size).offset((page - 1) * page_size)
        )
        .scalars()
        .all()
    )
    return {
        "items": [_to_out(db, m).model_dump() for m in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "", response_model=MarriageOut, status_code=status.HTTP_201_CREATED, summary="تسجيل زواج"
)
def create_marriage(
    payload: MarriageCreate, request: Request, db: DbSession, user: WriterUser
) -> MarriageOut:
    husband = db.get(Person, payload.husband_id)
    wife = db.get(Person, payload.wife_id)
    if husband is None or wife is None:
        raise NotFoundError(Messages.PERSON_NOT_FOUND)
    if husband.gender not in (None, "M") or wife.gender not in (None, "F"):
        raise ValidationError(Messages.MARRIAGE_PARTNERS_GENDER)

    duplicate = db.execute(
        select(func.count())
        .select_from(Marriage)
        .where(Marriage.husband_id == payload.husband_id, Marriage.wife_id == payload.wife_id)
    ).scalar_one()
    if duplicate:
        raise ConflictError(Messages.MARRIAGE_DUPLICATE)

    marriage = Marriage(
        husband_id=payload.husband_id,
        wife_id=payload.wife_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        status=payload.status,
        notes=payload.notes,
        created_by=user.id,
    )
    db.add(marriage)
    db.flush()
    audit_service.record(
        db,
        action=AuditAction.CREATE,
        user_id=user.id,
        username=user.username,
        entity="marriage",
        entity_id=marriage.id,
        details={"husband_id": husband.id, "wife_id": wife.id},
        ip=get_client_ip(request),
    )
    db.commit()
    db.refresh(marriage)
    return _to_out(db, marriage)


@router.patch("/{marriage_id}", response_model=MarriageOut, summary="تعديل زواج")
def update_marriage(
    marriage_id: int,
    payload: MarriageUpdate,
    request: Request,
    db: DbSession,
    user: WriterUser,
) -> MarriageOut:
    marriage = db.get(Marriage, marriage_id)
    if marriage is None:
        raise NotFoundError(Messages.MARRIAGE_NOT_FOUND)

    start = payload.start_date if "start_date" in payload.model_fields_set else marriage.start_date
    end = payload.end_date if "end_date" in payload.model_fields_set else marriage.end_date
    if start and end and end < start:
        raise ValidationError(Messages.MARRIAGE_END_BEFORE_START)

    for field in ("start_date", "end_date", "status", "notes"):
        if field in payload.model_fields_set:
            setattr(marriage, field, getattr(payload, field))

    audit_service.record(
        db,
        action=AuditAction.UPDATE,
        user_id=user.id,
        username=user.username,
        entity="marriage",
        entity_id=marriage.id,
        details={"changes": list(payload.model_fields_set)},
        ip=get_client_ip(request),
    )
    db.commit()
    db.refresh(marriage)
    return _to_out(db, marriage)


@router.delete(
    "/{marriage_id}",
    response_model=MarriageDeleteResult,
    summary="حذف زواج (مدير فقط)",
)
def delete_marriage(
    marriage_id: int, request: Request, db: DbSession, admin: AdminUser
) -> MarriageDeleteResult:
    marriage = db.get(Marriage, marriage_id)
    if marriage is None:
        raise NotFoundError(Messages.MARRIAGE_NOT_FOUND)
    db.delete(marriage)
    audit_service.record(
        db,
        action=AuditAction.DELETE,
        user_id=admin.id,
        username=admin.username,
        entity="marriage",
        entity_id=marriage_id,
        ip=get_client_ip(request),
    )
    db.commit()
    return MarriageDeleteResult(id=marriage_id, deleted=True, message="تم حذف سجل الزواج")
