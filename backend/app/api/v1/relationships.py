"""Relationship endpoints: parents, children, tree, relatives, finder."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import DbSession, ReaderUser, get_client_ip
from app.core.config import settings
from app.models.audit import AuditAction
from app.models.marriage import Marriage
from app.models.person import Person
from app.models.user import User
from app.schemas.person import PersonOut, PersonRef
from app.schemas.relationship import (
    AncestorItem,
    AncestorsResponse,
    ChildrenResponse,
    DescendantItem,
    DescendantsResponse,
    ParentsResponse,
    RelationshipPathStep,
    RelationshipResponse,
    RelativesResponse,
    SiblingItem,
    SiblingsResponse,
    SpouseItem,
    SpousesResponse,
    TreeLink,
    TreeNode,
    TreeResponse,
)
from app.services import audit_service
from app.services.person_service import PersonService
from app.services.relationship_service import RelationshipService
from app.utils import relations_labels as _labels

router = APIRouter(tags=["العلاقات"])


def _mask(role: str) -> bool:
    return role in settings.mask_roles


def _ref(person: Person) -> PersonRef:
    return PersonRef(
        id=person.id,
        full_name=person.full_name,
        gender=person.gender,
        birth_date=person.birth_date,
        death_date=person.death_date,
        birth_place=person.birth_place,
        father_id=person.father_id,
        mother_id=person.mother_id,
    )


def _get_person(db: Session, person_id: int) -> Person:
    return PersonService(db).get(person_id)


def _log(
    db: Session,
    user: User,
    request: Request,
    person_id: int,
    kind: str,
    **details: Any,
) -> None:
    audit_service.record(
        db,
        action=AuditAction.VIEW,
        user_id=user.id,
        username=user.username,
        entity="person_relationship",
        entity_id=person_id,
        details={"relationship": kind, **details},
        ip=get_client_ip(request),
    )
    db.commit()


@router.get(
    "/persons/{person_id}/parents",
    response_model=ParentsResponse,
    summary="الوالدان",
    description="يعيد الأب والأم مع قائمة الوالدين غير المسجلين (NULL).",
)
def get_parents(
    person_id: int, request: Request, db: DbSession, user: ReaderUser
) -> ParentsResponse:
    person = _get_person(db, person_id)
    data = RelationshipService(db).parents(person)
    _log(db, user, request, person_id, "parents")
    mask = _mask(user.role)
    return ParentsResponse(
        person_id=person_id,
        father=(
            PersonOut.from_model(data["father"], mask_national_id=mask) if data["father"] else None
        ),
        mother=(
            PersonOut.from_model(data["mother"], mask_national_id=mask) if data["mother"] else None
        ),
        missing=data["missing"],
    )


@router.get(
    "/persons/{person_id}/children",
    response_model=ChildrenResponse,
    summary="الأبناء",
)
def get_children(
    person_id: int, request: Request, db: DbSession, user: ReaderUser
) -> ChildrenResponse:
    person = _get_person(db, person_id)
    data = RelationshipService(db).children(person)
    _log(db, user, request, person_id, "children", total=data["total"])
    return ChildrenResponse(
        person_id=person_id,
        as_father=[_ref(p) for p in data["as_father"]],
        as_mother=[_ref(p) for p in data["as_mother"]],
        total=data["total"],
    )


@router.get(
    "/persons/{person_id}/siblings",
    response_model=SiblingsResponse,
    summary="الإخوة (كاملون ونصف)",
)
def get_siblings(
    person_id: int, request: Request, db: DbSession, user: ReaderUser
) -> SiblingsResponse:
    person = _get_person(db, person_id)
    data = RelationshipService(db).siblings(person)
    _log(db, user, request, person_id, "siblings", total=data["total"])
    return SiblingsResponse(
        person_id=person_id,
        full=[
            SiblingItem(
                **_ref(i["person"]).model_dump(), relation=i["relation"], sibling_type="full"
            )
            for i in data["full"]
        ],
        half_paternal=[
            SiblingItem(
                **_ref(i["person"]).model_dump(),
                relation="أخ من الأب",
                sibling_type="half_paternal",
            )
            for i in data["half_paternal"]
        ],
        half_maternal=[
            SiblingItem(
                **_ref(i["person"]).model_dump(),
                relation="أخت من الأم",
                sibling_type="half_maternal",
            )
            for i in data["half_maternal"]
        ],
        total=data["total"],
    )


@router.get(
    "/persons/{person_id}/spouses",
    response_model=SpousesResponse,
    summary="الأزواج",
)
def get_spouses(
    person_id: int, request: Request, db: DbSession, user: ReaderUser
) -> SpousesResponse:
    person = _get_person(db, person_id)
    rows = RelationshipService(db).spouses(person)
    _log(db, user, request, person_id, "spouses", total=len(rows))
    return SpousesResponse(
        person_id=person_id,
        spouses=[
            SpouseItem(
                **_ref(r["person"]).model_dump(),
                marriage_id=r["marriage_id"],
                status=r["status"],
                start_date=r["start_date"].isoformat() if r["start_date"] else None,
                end_date=r["end_date"].isoformat() if r["end_date"] else None,
                relation=r["relation"],
            )
            for r in rows
        ],
        total=len(rows),
    )


@router.get(
    "/persons/{person_id}/ancestors",
    response_model=AncestorsResponse,
    summary="الأجداد (تعمقي)",
    description="استعلام CTE تعاودي. depth=1 يعني الأب والأم فقط.",
)
def get_ancestors(
    person_id: int,
    request: Request,
    db: DbSession,
    user: ReaderUser,
    depth: Annotated[int, Query(ge=1, le=50)] = 3,
) -> AncestorsResponse:
    person = _get_person(db, person_id)
    matches = RelationshipService(db).ancestors(person, depth=depth)
    _log(db, user, request, person_id, "ancestors", depth=depth, total=len(matches))
    return AncestorsResponse(
        person_id=person_id,
        depth=depth,
        ancestors=[
            AncestorItem(
                **_ref(m.person).model_dump(),
                generation=abs(m.generation_diff),
                generation_label=m.relation,
                relation=m.relation,
            )
            for m in matches
        ],
        max_generation_found=max((abs(m.generation_diff) for m in matches), default=0),
        total=len(matches),
    )


@router.get(
    "/persons/{person_id}/descendants",
    response_model=DescendantsResponse,
    summary="الأبناء والأحفاد (تعمقي)",
)
def get_descendants(
    person_id: int,
    request: Request,
    db: DbSession,
    user: ReaderUser,
    depth: Annotated[int, Query(ge=1, le=50)] = 3,
) -> DescendantsResponse:
    person = _get_person(db, person_id)
    matches = RelationshipService(db).descendants(person, depth=depth)
    _log(db, user, request, person_id, "descendants", depth=depth, total=len(matches))
    return DescendantsResponse(
        person_id=person_id,
        depth=depth,
        descendants=[
            DescendantItem(
                **_ref(m.person).model_dump(),
                generation=m.generation_diff,
                generation_label=m.relation,
                relation=m.relation,
            )
            for m in matches
        ],
        max_generation_found=max((m.generation_diff for m in matches), default=0),
        total=len(matches),
    )


@router.get(
    "/persons/{person_id}/tree",
    response_model=TreeResponse,
    summary="شجرة العائلة جاهزة للعرض",
    description="up = عدد أجيال الأجداد، down = عدد أجيال النسل. Couples are completed automatically.",
)
def get_tree(
    person_id: int,
    request: Request,
    db: DbSession,
    user: ReaderUser,
    up: Annotated[int, Query(ge=0, le=10)] = 3,
    down: Annotated[int, Query(ge=0, le=10)] = 4,
    max_nodes: Annotated[int, Query(ge=10, le=5000)] = 800,
) -> TreeResponse:
    person = _get_person(db, person_id)
    data = RelationshipService(db).tree(person, up=up, down=down, max_nodes=max_nodes)
    _log(db, user, request, person_id, "tree", up=up, down=down, nodes=data["total_nodes"])
    return TreeResponse(
        person_id=person_id,
        up=up,
        down=down,
        nodes=[TreeNode(**node) for node in data["nodes"]],
        links=[TreeLink(**link) for link in data["links"]],
        marriages=data["marriages"],
        total_nodes=data["total_nodes"],
        truncated=data["truncated"],
    )


@router.get(
    "/persons/{person_id}/relatives",
    response_model=RelativesResponse,
    summary="الأقارب",
    description="الأخوات والعمات، الأبناء من الإخوة، أبناء العم، والصلات بالزواج.",
)
def get_relatives(
    person_id: int,
    request: Request,
    db: DbSession,
    user: ReaderUser,
) -> RelativesResponse:
    person = _get_person(db, person_id)
    data = RelationshipService(db).relatives(person)
    _log(db, user, request, person_id, "relatives", total=sum(len(v) for v in data.values()))

    def convert(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                **_ref(m.person).model_dump(),
                "relation": m.relation,
                "relation_code": m.code,
                "generation_diff": m.generation_diff,
                "path": m.path,
            }
            for m in items
        ]

    return RelativesResponse(
        person_id=person_id,
        uncles_aunts=convert(data["uncles_aunts"]),
        cousins=convert(data["cousins"]),
        nephews_nieces=convert(data["nephews_nieces"]),
        in_laws=convert(data["in_laws"]),
        grand_uncles=convert(data["grand_uncles"]),
        grand_aunts=convert(data["grand_aunts"]),
        summary={k: len(v) for k, v in data.items()},
    )


@router.get(
    "/relationship",
    response_model=RelationshipResponse,
    summary="البحث عن صلة القرابة بين شخصين",
    description="يعيد نوع العلاقة بالعربية مع المسار الأقصر عبر السلف المشترك.",
)
def find_relationship(
    request: Request,
    db: DbSession,
    user: ReaderUser,
    a: int = Query(..., gt=0, description="معرف الشخص الأول"),
    b: int = Query(..., gt=0, description="معرف الشخص الثاني"),
) -> RelationshipResponse:
    result = RelationshipService(db).relationship(a, b)
    _log(db, user, request, a, "relationship", other=b, relation=result.relation)

    persons = {a, b}
    persons.update(result.path)
    if result.common_ancestor:
        persons.add(result.common_ancestor.id)
    rows = db.execute(select(Person).where(Person.id.in_(persons))).scalars().all()
    people = {p.id: p for p in rows}

    def _person(pid: int) -> Person | None:
        return people.get(pid)

    def _step_link(u_id: int, v_id: int) -> str | None:
        """How ``v`` is related to ``u``: parent, child, spouse or unknown."""
        u, v = _person(u_id), _person(v_id)
        if u is None or v is None:
            return None
        if v.father_id == u_id or v.mother_id == u_id:
            return _labels.lineal_descendant_label(1, v.gender)
        if u.father_id == v_id or u.mother_id == v_id:
            return _labels.lineal_ancestor_label(1, v.gender)
        linked = db.execute(
            select(Marriage).where(
                ((Marriage.husband_id == u_id) & (Marriage.wife_id == v_id))
                | ((Marriage.husband_id == v_id) & (Marriage.wife_id == u_id))
            )
        ).scalars().first()
        if linked is not None:
            return "الزوجة" if v.gender == "F" else "الزوج"
        return None

    # A self-comparison has a single-element path, so never overwrite a role
    # with ``None`` for the same person id.
    roles: dict[int, str] = {}
    if result.path:
        roles[result.path[0]] = "الشخص الأول"
        if len(result.path) > 1:
            roles[result.path[-1]] = "الشخص الثاني"
    if result.common_ancestor:
        roles[result.common_ancestor.id] = "أقرب سلف مشترك"

    steps = [
        RelationshipPathStep(
            person_id=pid,
            full_name=_person(pid).full_name if _person(pid) else str(pid),
            gender=_person(pid).gender if _person(pid) else None,
            role=roles.get(pid, "قريب"),
            relation_to_next=(
                _step_link(pid, result.path[i + 1]) if i + 1 < len(result.path) else None
            ),
        )
        for i, pid in enumerate(result.path)
    ]

    return RelationshipResponse(
        a=a,
        b=b,
        relation=result.relation,
        relation_code=result.code,
        generations=result.generations,
        common_ancestor_id=result.common_ancestor.id if result.common_ancestor else None,
        common_ancestor_name=(result.common_ancestor.full_name if result.common_ancestor else None),
        path=steps,
        distance=result.distance,
        relation_from_a=result.relation_from_a,
        relation_from_b=result.relation_from_b,
        explanation=result.explanation,
    )


@router.get(
    "/persons/{person_id}/family-summary",
    response_model=dict,
    summary="ملخص عائلة الشخص",
    description="كل العدادات في استدعاء واحد - تستخدمه صفحة تفاصيل الشخص.",
)
def family_summary(person_id: int, request: Request, db: DbSession, user: ReaderUser) -> dict:
    person = _get_person(db, person_id)
    service = RelationshipService(db)
    children = service.children(person)
    siblings = service.siblings(person)
    spouses = service.spouses(person)
    descendants = len(service.descendant_map(person.id, 20))
    ancestors = len(service.ancestor_map(person.id, 20))
    marriages_count = db.execute(
        select(func.count())
        .select_from(Marriage)
        .where((Marriage.husband_id == person_id) | (Marriage.wife_id == person_id))
    ).scalar_one()
    _log(db, user, request, person_id, "family_summary")
    return {
        "person_id": person_id,
        "children": children["total"],
        "siblings": siblings["total"],
        "spouses": len(spouses),
        "descendants": descendants,
        "ancestors": ancestors,
        "marriages": int(marriages_count),
    }
