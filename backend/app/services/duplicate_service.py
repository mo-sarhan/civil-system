"""Duplicate detection and merge."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.person import Person
from app.utils.arabic import normalize_name, similarity

#: Two people are "probably duplicates" when the trigram score is at least this.
SIMILARITY_THRESHOLD = 0.6

_DUPLICATE_NATIONAL_ID_SQL = """
SELECT id, national_id, full_name, gender, birth_date, birth_place, father_id, mother_id
FROM person
WHERE national_id IS NOT NULL
  AND merged_into_id IS NULL
  AND id IN (
      SELECT id FROM (
          SELECT id, ROW_NUMBER() OVER (PARTITION BY national_id ORDER BY id) AS rn
          FROM person WHERE national_id IS NOT NULL AND merged_into_id IS NULL
      ) t WHERE rn > 1
  )
ORDER BY national_id, id
"""

_DUPLICATE_NAME_BIRTH_SQL = """
SELECT p.id, p.full_name, p.full_name_normalized, p.gender, p.birth_date, p.birth_place,
       p.father_id, p.mother_id
FROM person p
WHERE p.merged_into_id IS NULL
  AND p.birth_date IS NOT NULL
  AND p.id IN (
      SELECT id FROM (
          SELECT id, ROW_NUMBER() OVER (
              PARTITION BY full_name_normalized, birth_date ORDER BY id
          ) AS rn
          FROM person WHERE merged_into_id IS NULL AND birth_date IS NOT NULL
      ) t WHERE rn > 1
  )
ORDER BY p.full_name_normalized, p.birth_date, p.id
"""

#: Candidate pairs for the fuzzy pass: same birth year plus a shared name
#: token. The final score is computed in Python (see ``_fuzzy_candidates``).
_FUZZY_CANDIDATES_SQL = """
SELECT a.id AS id_a, b.id AS id_b,
       a.full_name AS name_a, b.full_name AS name_b,
       a.full_name_normalized AS norm_a, b.full_name_normalized AS norm_b,
       a.birth_date AS birth_a, b.birth_date AS birth_b,
       a.gender AS gender_a, b.gender AS gender_b,
       a.birth_place AS place_a, b.birth_place AS place_b,
       a.father_id AS father_a, b.father_id AS father_b,
       a.mother_id AS mother_a, b.mother_id AS mother_b,
       a.national_id AS national_a, b.national_id AS national_b
FROM person a
JOIN person b
  ON a.id < b.id
 AND a.merged_into_id IS NULL
 AND b.merged_into_id IS NULL
 AND a.birth_date IS NOT NULL
 AND b.birth_date IS NOT NULL
 AND EXTRACT(YEAR FROM a.birth_date) = EXTRACT(YEAR FROM b.birth_date)
 AND (
        split_part(a.full_name_normalized, ' ', 1) = split_part(b.full_name_normalized, ' ', 1)
     OR split_part(a.full_name_normalized, ' ', 1) = split_part(b.full_name_normalized, ' ', 2)
     OR a.full_name_normalized = b.full_name_normalized
 )
ORDER BY a.id, b.id
LIMIT :limit
"""


class DuplicateService:
    """Find and merge probable duplicates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Detection
    # ------------------------------------------------------------------ #
    def find_duplicates(
        self,
        *,
        threshold: float = SIMILARITY_THRESHOLD,
        limit: int = 100,
        include_national_id: bool = True,
        include_name_birth: bool = True,
    ) -> dict[str, Any]:
        """Return groups of probable duplicates."""
        groups: dict[tuple, dict[str, Any]] = {}

        if include_national_id:
            for row in self.db.execute(text(_DUPLICATE_NATIONAL_ID_SQL)).mappings():
                self._add(
                    groups,
                    key=("national_id", row["national_id"]),
                    person_id=row["id"],
                    reason="تطابق رقم القومى",
                    confidence=1.0,
                    row=row,
                )

        if include_name_birth:
            for row in self.db.execute(text(_DUPLICATE_NAME_BIRTH_SQL)).mappings():
                self._add(
                    groups,
                    key=("name_birth", row["full_name_normalized"], row["birth_date"]),
                    person_id=row["id"],
                    reason="تطابق الاسم وتاريخ الميلاد",
                    confidence=0.95,
                    row=row,
                )

        # Fuzzy name + same birth date, evaluated in Python on a bounded slice.
        candidates = self._fuzzy_candidates(threshold, limit)
        for group in candidates:
            self._add(
                groups,
                key=("fuzzy", group["key"]),
                person_id=group["id"],
                reason=group["reason"],
                confidence=group["confidence"],
                row=group["row"],
            )

        result_groups = [group for group in groups.values() if len(group["persons"]) > 1]
        result_groups.sort(key=lambda g: (-g["confidence"], g["persons"][0]["id"]))

        return {
            "groups": result_groups[:limit],
            "total_groups": len(result_groups),
            "threshold": threshold,
        }

    def _add(
        self,
        groups: dict[tuple, dict[str, Any]],
        *,
        key: tuple,
        person_id: int,
        reason: str,
        confidence: float,
        row: Any,
    ) -> None:
        group = groups.setdefault(
            key,
            {
                "key": ":".join(str(k) for k in key),
                "reason": reason,
                "confidence": confidence,
                "persons": [],
            },
        )
        if any(p["id"] == person_id for p in group["persons"]):
            return
        group["persons"].append(
            {
                "id": row["id"],
                "full_name": row["full_name"],
                "gender": row.get("gender"),
                "birth_date": row["birth_date"],
                "birth_place": row.get("birth_place"),
                "father_id": row.get("father_id"),
                "mother_id": row.get("mother_id"),
                "national_id": row.get("national_id"),
                "reasons": [],
                "confidences": [],
            }
        )
        group["persons"][-1]["reasons"].append(reason)
        group["persons"][-1]["confidences"].append(confidence)

    def _fuzzy_candidates(self, threshold: float, limit: int) -> list[dict[str, Any]]:
        """Names in the same birth year that are close enough to match.

        ``pg_trgm`` cannot be used as the prefilter here: with a ``C``
        collation its ``similarity()`` returns 0 for Arabic text, so the
        candidate pairs are selected by SQL on the birth year plus a shared
        name token and scored in Python by :func:`app.utils.arabic.similarity`.
        """
        rows = self.db.execute(text(_FUZZY_CANDIDATES_SQL), {"limit": limit}).mappings().all()
        results: list[dict[str, Any]] = []
        for row in rows:
            score = similarity(row["norm_a"], row["norm_b"])
            if score < threshold:
                continue
            norm_a = normalize_name(row["norm_a"])
            norm_b = normalize_name(row["norm_b"])
            reasons = ["تشابه في الاسم مع قرب تاريخ الميلاد"]
            if norm_a and norm_b and sorted(norm_a.split()) == sorted(norm_b.split()):
                reasons.append("الاسمان مكونان من نفس الكلمات")
            if row["birth_a"] == row["birth_b"]:
                reasons.append("تطابق تاريخ الميلاد")
            confidence = round(min(1.0, max(score, 0.7)), 3)
            for side in ("a", "b"):
                person_id = row[f"id_{side}"]
                results.append(
                    {
                        "key": f"fuzzy:{row['id_a']}:{row['id_b']}",
                        "id": person_id,
                        "reason": " / ".join(reasons),
                        "confidence": confidence,
                        "row": {
                            "id": person_id,
                            "full_name": row[f"name_{side}"],
                            "gender": row[f"gender_{side}"],
                            "birth_date": row[f"birth_{side}"],
                            "birth_place": row[f"place_{side}"],
                            "father_id": row[f"father_{side}"],
                            "mother_id": row[f"mother_{side}"],
                            "national_id": row[f"national_{side}"],
                        },
                    }
                )
        return results

    def compare(self, person_a_id: int, person_b_id: int) -> dict[str, Any]:
        """Field-by-field comparison used by the side-by-side review page."""
        from app.services.person_service import PersonService
        from app.services.relationship_service import RelationshipService

        service = PersonService(self.db)
        relationships = RelationshipService(self.db)
        a = service.get(person_a_id)
        b = service.get(person_b_id)
        fields = [
            "national_id",
            "full_name",
            "gender",
            "birth_date",
            "death_date",
            "birth_place",
            "father_id",
            "mother_id",
            "first_name",
            "father_name",
            "grandfather_name",
            "family_name",
            "notes",
        ]
        rows = []
        differences = 0
        for field in fields:
            value_a = getattr(a, field, None)
            value_b = getattr(b, field, None)
            if field in {
                "full_name",
                "first_name",
                "father_name",
                "grandfather_name",
                "family_name",
            }:
                same = normalize_name(str(value_a or "")) == normalize_name(str(value_b or ""))
            else:
                same = value_a == value_b
            if not same:
                differences += 1
            rows.append({"field": field, "a": value_a, "b": value_b, "same": same})

        return {
            "a": {
                "id": a.id,
                "full_name": a.full_name,
                "national_id": a.national_id,
                "gender": a.gender,
                "birth_date": a.birth_date,
                "birth_place": a.birth_place,
                "father_id": a.father_id,
                "mother_id": a.mother_id,
                "children": relationships.children(a)["total"],
                "spouses": len(relationships.spouses(a)),
                "notes": a.notes,
            },
            "b": {
                "id": b.id,
                "full_name": b.full_name,
                "national_id": b.national_id,
                "gender": b.gender,
                "birth_date": b.birth_date,
                "birth_place": b.birth_place,
                "father_id": b.father_id,
                "mother_id": b.mother_id,
                "children": relationships.children(b)["total"],
                "spouses": len(relationships.spouses(b)),
                "notes": b.notes,
            },
            "fields": rows,
            "differences": differences,
            "name_similarity": round(similarity(a.full_name, b.full_name), 4),
            "recommendation": self._recommend(a, b),
        }

    @staticmethod
    def _recommend(a: Person, b: Person) -> dict[str, Any]:
        """Suggest which record should survive the merge."""

        def score(p: Person) -> int:
            value = 0
            if p.national_id:
                value += 3
            if p.birth_date:
                value += 2
            if p.birth_place:
                value += 1
            if p.father_id:
                value += 2
            if p.mother_id:
                value += 1
            return value

        score_a, score_b = score(a), score(b)
        if score_a == score_b:
            return {"keep": a.id, "reason": "البيانات متساوية - القرار يدوي", "confidence": 0.5}
        keep = a.id if score_a > score_b else b.id
        return {
            "keep": keep,
            "reason": "السجل الأغنى بالبيانات والصلات",
            "confidence": round(abs(score_a - score_b) / max(1, score_a + score_b), 2),
        }
