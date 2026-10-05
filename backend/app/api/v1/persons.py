"""Person CRUD, listing, filtering, search and deletion endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, status

from app.api.deps import (
    AdminUser,
    DbSession,
    ReaderUser,
    WriterUser,
    get_client_ip,
)
from app.core.pagination import Page, Pagination
from app.models.audit import AuditAction
from app.schemas.person import (
    PersonCreate,
    PersonDeleteResult,
    PersonOut,
    PersonSearchResult,
    PersonUpdate,
)
from app.services import audit_service
from app.services.person_service import PersonService

router = APIRouter(prefix="/persons", tags=["الأشخاص"])


def _mask_national_id(role: str, masked_roles: set[str]) -> bool:
    return role in masked_roles


@router.get(
    "",
    response_model=Page[PersonOut],
    summary="قائمة الأشخاص (مقسم صفحات)",
    description="دعم البحث والتصفية: النوع، سنة الميلاد، مكان الميلاد، وجود الوالدين، رقم القومى.",
)
def list_persons(
    db: DbSession,
    user: ReaderUser,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=500),
    q: Annotated[str | None, Query(description="بحث بالاسم أو رقم القومى")] = None,
    gender: Annotated[Literal["M", "F"] | None, Query()] = None,
    birth_year_from: int | None = None,
    birth_year_to: int | None = None,
    birth_place: str | None = None,
    father_id: int | None = None,
    mother_id: int | None = None,
    has_father: bool | None = None,
    has_mother: bool | None = None,
    has_national_id: bool | None = None,
    alive: bool | None = None,
    national_id: str | None = None,
    sort: Literal["full_name", "birth_date", "id", "created_at", "updated_at"] = "full_name",
    direction: Literal["asc", "desc"] = "asc",
) -> Page[PersonOut]:
    """Paginated people list with fuzzy search and filters."""
    service = PersonService(db)
    pagination = Pagination.from_query(page, page_size)
    page_result = service.list_persons(
        pagination=pagination,
        q=q,
        gender=gender,
        birth_year_from=birth_year_from,
        birth_year_to=birth_year_to,
        birth_place=birth_place,
        father_id=father_id,
        mother_id=mother_id,
        has_father=has_father,
        has_mother=has_mother,
        has_national_id=has_national_id,
        alive=alive,
        national_id=national_id,
        sort=sort,
        direction=direction,
    )

    from app.core.config import settings

    mask = _mask_national_id(user.role, settings.mask_roles)
    items = [PersonOut.from_model(p, mask_national_id=mask) for p in page_result.items]

    if q:
        audit_service.record(
            db,
            action=AuditAction.SEARCH,
            user_id=user.id,
            username=user.username,
            entity="person",
            details={
                "query": q,
                "results": page_result.total,
                "filters": {
                    k: v
                    for k, v in {
                        "gender": gender,
                        "birth_year_from": birth_year_from,
                        "birth_year_to": birth_year_to,
                        "birth_place": birth_place,
                    }.items()
                    if v is not None
                },
            },
            ip=get_client_ip(request),
        )
        db.commit()

    return Page.build(items, page_result.total, page_result.page, page_result.page_size)


@router.get(
    "/search",
    response_model=list[PersonSearchResult],
    summary="بحث سريع بالاسم أو رقم القومى",
    description="بحث تقريبي (trigram) مع تطبيع النص العربي وإخفاء التطابقات.",
)
def search_persons(
    db: DbSession,
    user: ReaderUser,
    request: Request,
    q: Annotated[str, Query(min_length=2, max_length=120)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PersonSearchResult]:
    service = PersonService(db)
    results = service.search(q, limit=limit)

    from app.core.config import settings

    mask = _mask_national_id(user.role, settings.mask_roles)
    audit_service.record(
        db,
        action=AuditAction.SEARCH,
        user_id=user.id,
        username=user.username,
        entity="person",
        details={"query": q, "results": len(results)},
        ip=get_client_ip(request),
    )
    db.commit()

    return [
        PersonSearchResult(
            person=PersonOut.from_model(person, mask_national_id=mask),
            score=score,
            matched_by=matched_by,
        )
        for person, score, matched_by in results
    ]


@router.post(
    "",
    response_model=PersonOut,
    status_code=status.HTTP_201_CREATED,
    summary="إنشاء سجل شخص",
)
def create_person(
    payload: PersonCreate, request: Request, db: DbSession, user: WriterUser
) -> PersonOut:
    person = PersonService(db).create(payload, user_id=user.id, ip=get_client_ip(request))
    return PersonOut.from_model(person)


@router.get(
    "/{person_id}",
    response_model=PersonOut,
    summary="تفاصيل شخص",
    description="يتم تسجيل عملية العرض في سجل التدقيق لكل مستخدم.",
)
def get_person(person_id: int, request: Request, db: DbSession, user: ReaderUser) -> PersonOut:
    service = PersonService(db)
    person = service.get(person_id)
    audit_service.record(
        db,
        action=AuditAction.VIEW,
        user_id=user.id,
        username=user.username,
        entity="person",
        entity_id=person.id,
        details={"full_name": person.full_name},
        ip=get_client_ip(request),
    )
    db.commit()

    from app.core.config import settings

    mask = _mask_national_id(user.role, settings.mask_roles)
    return PersonOut.from_model(person, mask_national_id=mask)


@router.patch("/{person_id}", response_model=PersonOut, summary="تعديل سجل شخص")
def update_person(
    person_id: int,
    payload: PersonUpdate,
    request: Request,
    db: DbSession,
    user: WriterUser,
) -> PersonOut:
    service = PersonService(db)
    person = service.get(person_id)
    updated = service.update(person, payload, user_id=user.id, ip=get_client_ip(request))
    return PersonOut.from_model(updated)


@router.delete(
    "/{person_id}",
    response_model=PersonDeleteResult,
    summary="حذف سجل شخص (مدير فقط)",
)
def delete_person(
    person_id: int, request: Request, db: DbSession, admin: AdminUser
) -> PersonDeleteResult:
    service = PersonService(db)
    person = service.get(person_id)
    service.delete(person, user_id=admin.id, ip=get_client_ip(request))
    return PersonDeleteResult(id=person_id, deleted=True, message="تم حذف السجل بنجاح")
