"""Import wizard endpoints: upload, preview, map, validate, commit, report."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, File, Query, Request, UploadFile
from fastapi.responses import PlainTextResponse

from app.api.deps import DbSession, ImporterUser, get_client_ip
from app.core.config import settings
from app.core.exceptions import PayloadTooLargeError, ValidationError
from app.models.audit import AuditAction
from app.models.import_job import ImportJob, ImportStatus
from app.services import audit_service
from app.services.import_service import (
    FIELD_DEFINITIONS,
    LINKING_MODES,
    ImportService,
    build_csv_template,
    count_rows,
    validate_upload,
)
from app.utils.messages import Messages

router = APIRouter(prefix="/imports", tags=["الاستيراد"])

#: Hard ceiling on upload size (bytes).
MAX_UPLOAD_BYTES = 512 * 1024 * 1024


@router.get("/fields", response_model=dict, summary="الحقول المتاحة للربط")
def fields(_user: ImporterUser) -> dict[str, Any]:
    """Describes every mappable field plus the linking modes."""
    return {
        "fields": [
            {
                "key": key,
                "label": meta["label"],
                "required": meta["required"],
                "aliases": meta["aliases"],
            }
            for key, meta in FIELD_DEFINITIONS.items()
        ],
        "linking_modes": [{"key": key, "label": label} for key, label in LINKING_MODES.items()],
        "max_rows": settings.import_max_rows,
        "chunk_size": settings.import_chunk_size,
    }


@router.get("/template/csv", summary="تحميل قالب CSV")
def csv_template(_user: ImporterUser) -> PlainTextResponse:
    """Blank CSV with the canonical column order and two sample rows."""
    content = build_csv_template()
    return PlainTextResponse(
        content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="civil_registry_template.csv"'},
    )


@router.post("/upload", response_model=dict, status_code=201, summary="رفع ملف")
async def upload(
    request: Request,
    db: DbSession,
    user: ImporterUser,
    file: Annotated[UploadFile, File(description="CSV أو XLSX")],
) -> dict[str, Any]:
    """Store the file, count its rows and return the 20-row preview."""
    if not file.filename:
        raise ValidationError("لم يتم إرسال أي ملف")
    file_type, path = validate_upload(file.filename, 0)

    size = 0
    with path.open("wb") as handle:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                handle.close()
                path.unlink(missing_ok=True)
                raise PayloadTooLargeError("حجم الملف يتجاوز 512 ميجابايت")
            handle.write(chunk)

    if size == 0:
        path.unlink(missing_ok=True)
        raise ValidationError(Messages.IMPORT_FILE_EMPTY)

    total = count_rows(path)
    if total == 0:
        path.unlink(missing_ok=True)
        raise ValidationError(Messages.IMPORT_FILE_EMPTY)
    if total > settings.import_max_rows:
        path.unlink(missing_ok=True)
        raise PayloadTooLargeError(
            f"عدد الصفوف ({total}) يتجاوز الحد المسموح ({settings.import_max_rows})"
        )

    job = ImportJob(
        filename=file.filename,
        stored_path=str(path),
        file_type=file_type,
        total_rows=total,
        status=ImportStatus.PENDING.value,
        created_by=user.id,
    )
    db.add(job)
    db.flush()

    audit_service.record(
        db,
        action=AuditAction.IMPORT,
        user_id=user.id,
        username=user.username,
        entity="import_job",
        entity_id=job.id,
        details={"filename": job.filename, "total_rows": total},
        ip=get_client_ip(request),
    )
    db.commit()
    db.refresh(job)

    service = ImportService(db)
    return {"job": _job_out(job), "preview": service.preview(job)}


@router.get("/jobs", response_model=dict, summary="قائمة مهام الاستيراد")
def list_jobs(db: DbSession, user: ImporterUser, limit: int = Query(50, ge=1, le=200)) -> dict:
    jobs = ImportService(db).list_jobs(limit=limit)
    return {"items": [_job_out(j) for j in jobs], "total": len(jobs)}


@router.get("/jobs/{job_id}", response_model=dict, summary="حالة مهمة استيراد")
def get_job(db: DbSession, user: ImporterUser, job_id: int) -> dict[str, Any]:
    job = ImportService(db).get_job(job_id)
    return {"job": _job_out(job, include_report=True)}


@router.get("/jobs/{job_id}/preview", response_model=dict, summary="معاينة أول 20 صف")
def preview(
    job_id: int, db: DbSession, user: ImporterUser, rows: int = Query(20, ge=1, le=100)
) -> dict:
    job = ImportService(db).get_job(job_id)
    return ImportService(db).preview(job, rows=rows)


@router.post("/jobs/{job_id}/mapping", response_model=dict, summary="حفظ مطابقة الأعمدة")
def set_mapping(
    job_id: int,
    db: DbSession,
    user: ImporterUser,
    mapping: Annotated[dict[str, int], Body(embed=True)],
    linking_mode: Annotated[str, Body(embed=True)] = "none",
) -> dict[str, Any]:
    """``{"mapping": {"full_name": 1, ...}, "linking_mode": "by_national_id"}``."""
    job = ImportService(db).get_job(job_id)
    updated = ImportService(db).set_mapping(job, mapping, linking_mode, actor_id=user.id)
    return {"job": _job_out(updated)}


@router.post("/jobs/{job_id}/validate", response_model=dict, summary="التحقق قبل الحفظ")
def validate_job(job_id: int, db: DbSession, user: ImporterUser) -> dict[str, Any]:
    """Full validation pass; returns an Arabic error report and writes nothing."""
    service = ImportService(db)
    job = service.get_job(job_id)
    report = service.validate(job)
    audit_service.record(
        db,
        action=AuditAction.IMPORT,
        user_id=user.id,
        username=user.username,
        entity="import_job",
        entity_id=job.id,
        details={"stage": "validate", **report},
    )
    db.commit()
    return report


@router.post("/jobs/{job_id}/commit", response_model=dict, summary="تنفيذ الاستيراد")
def commit_job(
    job_id: int,
    request: Request,
    db: DbSession,
    user: ImporterUser,
    skip_invalid: Annotated[bool, Body(embed=True)] = True,
) -> dict[str, Any]:
    """Start the background upsert. Poll ``GET /imports/jobs/{id}`` for progress."""
    service = ImportService(db)
    job = service.get_job(job_id)
    job = service.commit_async(job, actor_id=user.id, skip_invalid=skip_invalid)
    audit_service.record(
        db,
        action=AuditAction.IMPORT,
        user_id=user.id,
        username=user.username,
        entity="import_job",
        entity_id=job.id,
        details={"stage": "commit", "skip_invalid": skip_invalid},
        ip=get_client_ip(request),
    )
    db.commit()
    return {"job": _job_out(job), "message": "بدأ الاستيراد في الخلفية"}


@router.delete("/jobs/{job_id}", response_model=dict, summary="حذف مهمة استيراد")
def delete_job(job_id: int, db: DbSession, user: ImporterUser) -> dict[str, str]:
    service = ImportService(db)
    job = service.get_job(job_id)
    from pathlib import Path

    if job.stored_path:
        Path(job.stored_path).unlink(missing_ok=True)
    db.delete(job)
    db.commit()
    return {"message": "تم حذف مهمة الاستيراد"}


@router.get("/mapping-templates", response_model=dict, summary="قوالب المطابقة المحفوظة")
def list_templates(db: DbSession, user: ImporterUser) -> dict:
    templates = ImportService(db).list_mapping_templates(user.id)
    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "description": t.description,
                "mapping": t.mapping,
                "linking_mode": t.linking_mode,
                "is_shared": t.is_shared,
                "created_by": t.created_by,
                "created_at": t.created_at,
            }
            for t in templates
        ]
    }


@router.post("/mapping-templates", status_code=201, response_model=dict, summary="حفظ قالب مطابقة")
def create_template(
    db: DbSession,
    user: ImporterUser,
    name: Annotated[str, Body(embed=True, min_length=2, max_length=120)],
    mapping: Annotated[dict[str, int], Body(embed=True)],
    linking_mode: Annotated[str, Body(embed=True)] = "none",
    description: Annotated[str | None, Body(embed=True)] = None,
    is_shared: Annotated[bool, Body(embed=True)] = True,
) -> dict[str, Any]:
    template = ImportService(db).create_mapping_template(
        name=name,
        mapping=mapping,
        linking_mode=linking_mode,
        description=description,
        is_shared=is_shared,
        user_id=user.id,
    )
    return {
        "id": template.id,
        "name": template.name,
        "mapping": template.mapping,
        "linking_mode": template.linking_mode,
    }


@router.delete("/mapping-templates/{template_id}", response_model=dict, summary="حذف قالب")
def delete_template(template_id: int, db: DbSession, user: ImporterUser) -> dict[str, str]:
    ImportService(db).delete_mapping_template(template_id)
    return {"message": "تم حذف القالب"}


def _job_out(job: ImportJob, *, include_report: bool = False) -> dict[str, Any]:
    """Serialise a job for the UI progress bar."""
    data = {
        "id": job.id,
        "filename": job.filename,
        "file_type": job.file_type,
        "status": job.status,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows,
        "success_rows": job.success_rows,
        "failed_rows": job.failed_rows,
        "created_rows": job.created_rows,
        "updated_rows": job.updated_rows,
        "progress": job.progress,
        "linking_mode": job.linking_mode,
        "column_mapping": job.column_mapping,
        "message": job.message,
        "created_by": job.created_by,
        "created_at": job.created_at,
        "committed_at": job.committed_at,
    }
    if include_report:
        data["error_report"] = job.error_report or []
        data["warnings"] = job.warnings or []
    return data
