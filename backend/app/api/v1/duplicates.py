"""Duplicate review and merge endpoints (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Body, Query, Request

from app.api.deps import AdminUser, DbSession, get_client_ip
from app.models.audit import AuditAction
from app.schemas.person import PersonOut
from app.services import audit_service
from app.services.duplicate_service import DuplicateService
from app.services.person_service import PersonService

router = APIRouter(prefix="/duplicates", tags=["المكررات"])


@router.get("", response_model=dict, summary="اكتشاف السجلات المكررة")
def find_duplicates(
    db: DbSession,
    admin: AdminUser,
    request: Request,
    threshold: float = Query(0.6, ge=0.1, le=1.0),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Group probable duplicates by identical national ID, name+birth date, or fuzzy name."""
    data = DuplicateService(db).find_duplicates(threshold=threshold, limit=limit)
    audit_service.record(
        db,
        action=AuditAction.VIEW,
        user_id=admin.id,
        username=admin.username,
        entity="duplicates",
        details={"groups": data["total_groups"], "threshold": threshold},
        ip=get_client_ip(request),
    )
    db.commit()
    return data


@router.get("/compare", response_model=dict, summary="مقارنة سجلين")
def compare(
    db: DbSession,
    admin: AdminUser,
    a: int = Query(..., gt=0),
    b: int = Query(..., gt=0),
) -> dict:
    """Field-by-field diff plus a merge recommendation."""
    return DuplicateService(db).compare(a, b)


@router.post("/merge", response_model=dict, summary="دمج سجلين (مدير فقط)")
def merge(
    db: DbSession,
    admin: AdminUser,
    request: Request,
    target_id: int = Body(..., embed=True, description="السجل الذي سيبقى"),
    source_id: int = Body(..., embed=True, description="السجل الذي سيُدمج"),
) -> dict:
    """Re-point every reference from ``source_id`` to ``target_id`` and log it."""
    service = PersonService(db)
    target = service.get(target_id)
    source = service.get(source_id)
    stats = service.merge(
        target,
        source,
        user_id=admin.id,
        username=admin.username,
        ip=get_client_ip(request),
    )
    return {
        "message": "تم الدمج بنجاح",
        "target": PersonOut.model_validate(target).model_dump(mode="json"),
        "stats": stats,
    }
