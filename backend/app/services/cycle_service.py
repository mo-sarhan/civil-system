"""Cycle detection using a recursive CTE.

The person graph is a DAG by construction: ``father_id``/``mother_id`` point
from a child to older people.  Before saving we ask PostgreSQL whether the
proposed link would close a loop.  The same query shape is used by the
database trigger, so the application check and the DB check agree.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Walks up from ``(:person_id)`` through parents and returns every ancestor id.
ANCESTORS_CTE = """
WITH RECURSIVE ancestors AS (
    SELECT id AS id FROM person WHERE id = :person_id
    UNION ALL
    SELECT p.id
    FROM person p
    JOIN ancestors a ON p.id IN (a.father_id, a.mother_id)
)
SELECT DISTINCT id FROM ancestors
"""


def would_create_cycle(
    db: Session,
    person_id: int,
    father_id: int | None,
    mother_id: int | None,
) -> bool:
    """True when linking ``person_id`` to those parents closes a cycle."""
    if father_id is None and mother_id is None:
        return False
    if person_id in (father_id, mother_id):
        return True

    sql = """
    WITH RECURSIVE descendants AS (
        SELECT id FROM person WHERE id = :person_id
        UNION ALL
        SELECT c.id
        FROM person c
        JOIN descendants d ON c.father_id = d.id OR c.mother_id = d.id
    )
    SELECT 1 FROM descendants
    WHERE id = ANY(CAST(:parents AS BIGINT[]))
    LIMIT 1
    """
    result = db.execute(
        text(sql), {"person_id": person_id, "parents": _parent_ids(father_id, mother_id)}
    )
    return result.first() is not None


def is_descendant_of(
    db: Session, candidate_id: int, ancestor_id: int, max_depth: int = 100
) -> bool:
    """True when ``candidate_id`` is a descendant of ``ancestor_id``."""
    sql = text(
        """
        WITH RECURSIVE descendants AS (
            SELECT id, 1 AS depth FROM person WHERE id = :candidate
            UNION ALL
            SELECT c.id, d.depth + 1
            FROM person c JOIN descendants d ON c.father_id = d.id OR c.mother_id = d.id
            WHERE d.depth < :max_depth
        )
        SELECT 1 FROM descendants WHERE id = :ancestor LIMIT 1
        """
    )
    return (
        db.execute(
            sql, {"candidate": candidate_id, "ancestor": ancestor_id, "max_depth": max_depth}
        ).first()
        is not None
    )


def ancestor_ids(db: Session, person_id: int, max_depth: int = 50) -> set[int]:
    """All ancestor ids (excluding the person) up to ``max_depth``."""
    sql = text(
        """
        WITH RECURSIVE ancestors AS (
            SELECT id, father_id, mother_id, 1 AS depth FROM person WHERE id = :person
            UNION ALL
            SELECT p.id, p.father_id, p.mother_id, a.depth + 1
            FROM person p
            JOIN ancestors a ON p.id IN (a.father_id, a.mother_id)
            WHERE a.depth < :max_depth
        )
        SELECT DISTINCT id FROM ancestors WHERE depth > 1
        """
    )
    return {row[0] for row in db.execute(sql, {"person": person_id, "max_depth": max_depth})}


def descendant_ids(db: Session, person_id: int, max_depth: int = 50) -> set[int]:
    """All descendant ids (excluding the person) up to ``max_depth``."""
    sql = text(
        """
        WITH RECURSIVE descendants AS (
            SELECT id, 1 AS depth FROM person WHERE id = :person
            UNION ALL
            SELECT c.id, d.depth + 1
            FROM person c
            JOIN descendants d ON c.father_id = d.id OR c.mother_id = d.id
            WHERE d.depth < :max_depth
        )
        SELECT DISTINCT id FROM descendants WHERE depth > 1
        """
    )
    return {row[0] for row in db.execute(sql, {"person": person_id, "max_depth": max_depth})}


def _parent_ids(father_id: int | None, mother_id: int | None) -> list[int]:
    return [pid for pid in (father_id, mother_id) if pid is not None]
