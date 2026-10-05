"""Statistics for the dashboard."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import distinct, func, select

from app.api.deps import DbSession, ReaderUser
from app.models.marriage import Marriage
from app.models.person import Person

router = APIRouter(prefix="/stats", tags=["الإحصائيات"])


@router.get("", response_model=dict, summary="إحصائيات شاملة")
def overview(db: DbSession, _user: ReaderUser) -> dict:
    """Aggregated counts used by the dashboard cards."""
    total = db.execute(select(func.count()).select_from(Person)).scalar_one()
    active = db.execute(
        select(func.count()).select_from(Person).where(Person.merged_into_id.is_(None))
    ).scalar_one()
    males = db.execute(
        select(func.count()).select_from(Person).where(Person.gender == "M")
    ).scalar_one()
    females = db.execute(
        select(func.count()).select_from(Person).where(Person.gender == "F")
    ).scalar_one()
    unknown_gender = total - males - females

    alive = db.execute(
        select(func.count()).select_from(Person).where(Person.death_date.is_(None))
    ).scalar_one()
    deceased = total - alive

    with_national_id = db.execute(
        select(func.count()).select_from(Person).where(Person.national_id.isnot(None))
    ).scalar_one()
    with_birth_date = db.execute(
        select(func.count()).select_from(Person).where(Person.birth_date.isnot(None))
    ).scalar_one()

    missing_father = db.execute(
        select(func.count()).select_from(Person).where(Person.father_id.is_(None))
    ).scalar_one()
    missing_mother = db.execute(
        select(func.count()).select_from(Person).where(Person.mother_id.is_(None))
    ).scalar_one()

    marriages = db.execute(select(func.count()).select_from(Marriage)).scalar_one()
    active_marriages = db.execute(
        select(func.count()).select_from(Marriage).where(Marriage.status == "married")
    ).scalar_one()

    return {
        "total_persons": int(total),
        "active_persons": int(active),
        "merged_persons": int(total - active),
        "by_gender": {"M": int(males), "F": int(females), "unknown": int(unknown_gender)},
        "alive": int(alive),
        "deceased": int(deceased),
        "with_national_id": int(with_national_id),
        "without_national_id": int(total - with_national_id),
        "with_birth_date": int(with_birth_date),
        "missing_father": int(missing_father),
        "missing_mother": int(missing_mother),
        "marriages": int(marriages),
        "active_marriages": int(active_marriages),
    }


@router.get("/generations", response_model=dict, summary="عدد الأجيال")
def generations(db: DbSession, _user: ReaderUser) -> dict:
    """Approximate generation count using a recursive CTE."""
    from sqlalchemy import text

    sql = text(
        """
        WITH RECURSIVE roots AS (
            SELECT id FROM person
            WHERE father_id IS NULL AND mother_id IS NULL
        ),
        gen AS (
            SELECT id, 1 AS generation FROM roots
            UNION ALL
            SELECT c.id, g.generation + 1
            FROM person c
            JOIN gen g ON c.father_id = g.id OR c.mother_id = g.id
            WHERE g.generation < 60
        )
        SELECT COALESCE(MAX(generation), 0) AS max_generation,
               COUNT(DISTINCT id) AS reached
        FROM gen
        """
    )
    row = db.execute(sql).one()
    total = db.execute(select(func.count()).select_from(Person)).scalar_one()
    reached = int(row.reached)
    return {
        "max_generation": int(row.max_generation),
        "persons_with_lineage": reached,
        "persons_without_lineage": int(total - reached),
        "note": "الأجيال محسوبة للأشخاص الذين له سلف مسجل على الأقل",
    }


@router.get("/largest-families", response_model=dict, summary="أكبر العائلات")
def largest_families(db: DbSession, _user: ReaderUser, limit: int = 10) -> dict:
    """Family names ordered by the number of people sharing them."""
    rows = db.execute(
        select(
            Person.family_name,
            func.count().label("members"),
            func.count(Person.father_id).label("with_father"),
        )
        .where(Person.family_name.isnot(None))
        .group_by(Person.family_name)
        .order_by(func.count().desc(), Person.family_name)
        .limit(min(limit, 50))
    ).all()
    return {
        "items": [
            {
                "family_name": r.family_name,
                "members": int(r.members),
                "with_father_link": int(r.with_father),
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/birth-years", response_model=dict, summary="التوزيع حسب decade")
def birth_years(db: DbSession, _user: ReaderUser) -> dict:
    """Histogram of birth decades for the dashboard chart."""
    year = func.date_part("year", Person.birth_date)
    # The label is the birth decade itself (1985 -> 1980), not the decade in
    # which the person turned ten.
    decade = (func.floor(year / 10) * 10).label("decade")
    rows = db.execute(
        select(
            decade,
            func.count(),
            func.count().filter(Person.gender == "M"),
            func.count().filter(Person.gender == "F"),
        )
        .where(Person.birth_date.isnot(None))
        .group_by(decade)
        .order_by(decade)
    ).all()
    return {
        "items": [
            {"decade": int(r[0]), "total": int(r[1]), "male": int(r[2]), "female": int(r[3])}
            for r in rows
        ],
        "total": sum(int(r[1]) for r in rows),
    }


@router.get("/birth-places", response_model=dict, summary="أكبر أماكن الميلاد")
def birth_places(db: DbSession, _user: ReaderUser, limit: int = 10) -> dict:
    rows = db.execute(
        select(Person.birth_place, func.count().label("n"))
        .where(Person.birth_place.isnot(None))
        .group_by(Person.birth_place)
        .order_by(func.count().desc())
        .limit(min(limit, 50))
    ).all()
    return {"items": [{"birth_place": r.birth_place, "count": int(r.n)} for r in rows]}


@router.get("/missing-links", response_model=dict, summary="سجلات تنقصها صلة والد")
def missing_links(db: DbSession, _user: ReaderUser, limit: int = 50) -> dict:
    """People whose father link is missing - the main data-quality worklist."""
    rows = db.execute(
        select(
            Person.id,
            Person.full_name,
            Person.gender,
            Person.birth_date,
            Person.birth_place,
            Person.mother_id,
        )
        .where(Person.father_id.is_(None), Person.merged_into_id.is_(None))
        .order_by(func.coalesce(Person.birth_date, func.make_date(3000, 1, 1)).desc())
        .limit(limit)
    ).all()
    total = db.execute(
        select(func.count()).select_from(Person).where(Person.father_id.is_(None))
    ).scalar_one()
    return {
        "items": [
            {
                "id": r.id,
                "full_name": r.full_name,
                "gender": r.gender,
                "birth_date": r.birth_date,
                "birth_place": r.birth_place,
                "has_mother_link": r.mother_id is not None,
            }
            for r in rows
        ],
        "total": int(total),
    }


@router.get("/data-quality", response_model=dict, summary="مؤشرات جودة البيانات")
def data_quality(db: DbSession, _user: ReaderUser) -> dict:
    """Completeness percentages rendered as progress bars."""
    total = db.execute(select(func.count()).select_from(Person)).scalar_one() or 1
    checks = {
        "national_id": select(func.count())
        .select_from(Person)
        .where(Person.national_id.isnot(None)),
        "birth_date": select(func.count()).select_from(Person).where(Person.birth_date.isnot(None)),
        "gender": select(func.count()).select_from(Person).where(Person.gender.isnot(None)),
        "birth_place": select(func.count())
        .select_from(Person)
        .where(Person.birth_place.isnot(None)),
        "father_link": select(func.count()).select_from(Person).where(Person.father_id.isnot(None)),
        "mother_link": select(func.count()).select_from(Person).where(Person.mother_id.isnot(None)),
    }
    result = {}
    for key, stmt in checks.items():
        value = int(db.execute(stmt).scalar_one())
        result[key] = {"count": value, "percent": round(100.0 * value / total, 1)}
    return {"total": int(total), "fields": result}


@router.get("/search-suggestions", response_model=dict, summary="اقتراحات البحث السريعة")
def search_suggestions(db: DbSession, _user: ReaderUser, limit: int = 10) -> dict:
    """Most common family names, used to seed the search box."""
    rows = db.execute(
        select(Person.family_name, func.count().label("n"))
        .where(Person.family_name.isnot(None))
        .group_by(Person.family_name)
        .order_by(func.count().desc(), Person.family_name)
        .limit(min(limit, 25))
    ).all()
    places = (
        db.execute(
            select(distinct(Person.birth_place))
            .where(Person.birth_place.isnot(None))
            .limit(min(limit, 25))
        )
        .scalars()
        .all()
    )
    return {
        "family_names": [{"value": r.family_name, "count": int(r.n)} for r in rows],
        "birth_places": [p for p in places if p],
    }
