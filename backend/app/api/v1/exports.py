"""CSV / Excel export of search results."""

from __future__ import annotations

import csv
import io
import os
import tempfile
from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.api.deps import DbSession, ReaderUser, get_client_ip
from app.core.exceptions import ValidationError
from app.core.pagination import Pagination
from app.models.audit import AuditAction
from app.models.person import Person
from app.services import audit_service
from app.services.person_service import PersonService
from app.utils.messages import Messages

router = APIRouter(prefix="/export", tags=["التصدير"])

EXPORT_COLUMNS: list[tuple[str, str]] = [
    ("id", "المعرف"),
    ("national_id", "رقم القومى"),
    ("full_name", "الاسم الكامل"),
    ("first_name", "الاسم الأول"),
    ("father_name", "اسم الأب"),
    ("grandfather_name", "اسم الجد"),
    ("family_name", "اسم العائلة"),
    ("gender", "النوع"),
    ("birth_date", "تاريخ الميلاد"),
    ("death_date", "تاريخ الوفاة"),
    ("birth_place", "مكان الميلاد"),
    ("father_id", "معرف الأب"),
    ("mother_id", "معرف الأم"),
    ("notes", "ملاحظات"),
    ("created_at", "تاريخ الإنشاء"),
]

_GENDER_AR = {"M": "ذكر", "F": "أنثى", None: ""}


def _format(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _stream_people(filters: dict[str, Any], mask: bool, limit: int) -> Iterator[dict[str, str]]:
    """Yield export rows in batches so memory stays flat on huge result sets.

    The generator owns its session: a :class:`StreamingResponse` body is
    consumed after the request-scoped session has already been closed.
    """
    from app.db.session import SessionLocal
    from app.utils.national_id import mask_national_id

    # Batching is internal, so the public page-size cap does not apply here.
    page_size = 1000
    db = SessionLocal()
    try:
        service = PersonService(db)
        page = 1
        produced = 0
        while produced < limit:
            pagination = Pagination(page=page, page_size=page_size, offset=(page - 1) * page_size)
            result = service.list_persons(pagination=pagination, **filters)
            if not result.items:
                return
            for person in result.items:
                if mask and person.national_id:
                    national_id = mask_national_id(person.national_id)
                else:
                    national_id = _format(person.national_id)
                yield {
                    "id": str(person.id),
                    "national_id": national_id,
                    "full_name": person.full_name,
                    "first_name": _format(person.first_name),
                    "father_name": _format(person.father_name),
                    "grandfather_name": _format(person.grandfather_name),
                    "family_name": _format(person.family_name),
                    "gender": _GENDER_AR.get(person.gender, _format(person.gender)),
                    "birth_date": _format(person.birth_date),
                    "death_date": _format(person.death_date),
                    "birth_place": _format(person.birth_place),
                    "father_id": _format(person.father_id),
                    "mother_id": _format(person.mother_id),
                    "notes": _format(person.notes),
                    "created_at": _format(person.created_at),
                }
                produced += 1
                if produced >= limit:
                    return
            if produced >= result.total:
                return
            page += 1
    finally:
        db.close()


CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "المعرف"),
    ("national_id", "رقم القومى"),
    ("full_name", "الاسم الكامل"),
    ("first_name", "الاسم الأول"),
    ("father_name", "اسم الأب"),
    ("grandfather_name", "اسم الجد"),
    ("family_name", "اسم العائلة"),
    ("gender", "النوع"),
    ("birth_date", "تاريخ الميلاد"),
    ("death_date", "تاريخ الوفاة"),
    ("birth_place", "مكان الميلاد"),
    ("father_id", "معرف الأب"),
    ("mother_id", "معرف الأم"),
    ("notes", "ملاحظات"),
    ("created_at", "تاريخ الإنشاء"),
)


def _csv_response(rows: Iterator[dict[str, str]], filename: str) -> StreamingResponse:
    """UTF-8 CSV with a BOM so Excel opens Arabic text correctly."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=[label for _, label in CSV_COLUMNS])
    writer.writeheader()
    for row in rows:
        writer.writerow({label: row.get(key, "") for key, label in CSV_COLUMNS})

    payload = ("﻿" + buffer.getvalue()).encode("utf-8")
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _xlsx_response(rows: Iterator[dict[str, str]], filename: str) -> StreamingResponse:
    """XLSX workbook written to a temp file so memory stays bounded."""
    from openpyxl import Workbook

    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("السجلات")
    sheet.append([label for _, label in CSV_COLUMNS])
    for row in rows:
        sheet.append([row.get(key, "") for key, _ in CSV_COLUMNS])

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as handle:
        workbook.save(handle.name)
        temp_path = handle.name

    def body() -> Iterator[bytes]:
        try:
            with open(temp_path, "rb") as handle:
                while chunk := handle.read(64 * 1024):
                    yield chunk
        finally:
            os.unlink(temp_path)

    return StreamingResponse(
        body(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/persons", summary="تصدير نتائج البحث")
def export_persons(
    request: Request,
    db: DbSession,
    user: ReaderUser,
    format: Annotated[str, Query(pattern="^(csv|xlsx)$")] = "csv",
    q: str | None = None,
    gender: str | None = None,
    birth_year_from: int | None = None,
    birth_year_to: int | None = None,
    birth_place: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500_000)] = 10_000,
) -> StreamingResponse:
    """Stream the filtered people list as CSV or XLSX.

    The national ID is masked for roles that are not allowed to see it, exactly
    like in the UI.
    """
    from app.core.config import settings

    filters = {
        "q": q,
        "gender": gender,
        "birth_year_from": birth_year_from,
        "birth_year_to": birth_year_to,
        "birth_place": birth_place,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    service = PersonService(db)
    count_stmt = select(func.count()).select_from(Person).where(Person.merged_into_id.is_(None))
    from sqlalchemy import and_

    conditions = service._filter_conditions(**filters)
    if conditions:
        count_stmt = count_stmt.where(and_(*conditions))
    total = db.execute(count_stmt).scalar_one()
    # ``limit`` is how many rows the caller wants; the guard protects the
    # server, so it only fires when the whole result set is beyond the
    # configured hard ceiling.
    ceiling = settings.max_export_rows
    if total > ceiling:
        raise ValidationError(f"{Messages.EXPORT_TOO_LARGE} (المطابق {total}، الحد {ceiling})")
    row_budget = min(limit, ceiling)

    audit_service.record(
        db,
        action=AuditAction.EXPORT,
        user_id=user.id,
        username=user.username,
        entity="person",
        details={"format": format, "filters": filters, "rows": total},
        ip=get_client_ip(request),
    )
    db.commit()

    mask = user.role in settings.mask_roles
    rows = _stream_people(filters, mask, row_budget)
    stamp = "civil_registry_export"
    if format == "xlsx":
        return _xlsx_response(rows, f"{stamp}.xlsx")
    return _csv_response(rows, f"{stamp}.csv")


@router.get("/tree-csv", summary="تصدير شجرة شخص واحد")
def export_tree(
    request: Request,
    db: DbSession,
    user: ReaderUser,
    person_id: int = Query(..., gt=0),
    up: Annotated[int, Query(ge=0, le=10)] = 3,
    down: Annotated[int, Query(ge=0, le=10)] = 4,
) -> StreamingResponse:
    """Flat CSV of a person's tree: id, name, generation, parents."""
    from app.services.relationship_service import RelationshipService

    person = db.get(Person, person_id)
    if person is None:
        raise ValidationError(Messages.PERSON_NOT_FOUND)
    data = RelationshipService(db).tree(person, up=up, down=down)
    audit_service.record(
        db,
        action=AuditAction.EXPORT,
        user_id=user.id,
        username=user.username,
        entity="tree",
        entity_id=person.id,
        details={"up": up, "down": down, "nodes": len(data["nodes"])},
        ip=get_client_ip(request),
    )
    db.commit()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["المعرف", "الاسم", "الجيل", "رقم الأب", "رقم الأم", "تاريخ الميلاد"])
    for node in data["nodes"]:
        writer.writerow(
            [
                node["id"],
                node.get("full_name", ""),
                node.get("generation", ""),
                node.get("father_id") or "",
                node.get("mother_id") or "",
                _format(node.get("birth_date")),
            ]
        )
    return StreamingResponse(
        iter([("﻿" + buffer.getvalue()).encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="tree_{person_id}.csv"'},
    )
