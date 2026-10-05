"""Relationship engine.

Everything is computed with **recursive CTEs** so the cost stays proportional
to the size of the requested subtree, not to the size of the table.  The parent
indexes (``ix_person_father_id``, ``ix_person_mother_id``) turn the recursive
join into index lookups; see ``docs/PERFORMANCE.md`` for the EXPLAIN output.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.person import Person
from app.utils import relations_labels as labels
from app.utils.messages import Messages

#: Hard ceiling on generation walks, protects against corrupt data.
MAX_DEPTH = 50

#: Ancestors with the minimum generation distance.
#: Ancestors with the minimum generation distance (1 = father/mother).
#: The subject is the anchor at depth 0 and is filtered out of the result.
_ANCESTORS_SQL = """
WITH RECURSIVE anc AS (
    SELECT id, father_id, mother_id, 0 AS depth
    FROM person WHERE id = :person_id
    UNION ALL
    SELECT p.id, p.father_id, p.mother_id, a.depth + 1
    FROM person p
    JOIN anc a ON p.id = a.father_id OR p.id = a.mother_id
    WHERE a.depth < :max_depth
)
SELECT DISTINCT ON (id) id, depth FROM anc WHERE depth > 0 ORDER BY id, depth
"""

#: Descendants with the minimum generation distance (1 = son/daughter).
_DESCENDANTS_SQL = """
WITH RECURSIVE des AS (
    SELECT id, father_id, mother_id, 0 AS depth
    FROM person WHERE id = :person_id
    UNION ALL
    SELECT c.id, c.father_id, c.mother_id, d.depth + 1
    FROM person c
    JOIN des d ON c.father_id = d.id OR c.mother_id = d.id
    WHERE d.depth < :max_depth
)
SELECT DISTINCT ON (id) id, depth FROM des WHERE depth > 0 ORDER BY id, depth
"""

_SIBLINGS_SQL = """
WITH me AS (SELECT id, father_id, mother_id FROM person WHERE id = :person_id)
SELECT s.id,
       (me.father_id IS NOT NULL AND s.father_id = me.father_id) AS same_father,
       (me.mother_id IS NOT NULL AND s.mother_id = me.mother_id) AS same_mother
FROM person s
CROSS JOIN me
WHERE s.id <> me.id
  AND (
      (me.father_id IS NOT NULL AND s.father_id = me.father_id)
   OR (me.mother_id IS NOT NULL AND s.mother_id = me.mother_id)
  )
"""

_SPOUSES_SQL = """
SELECT m.id AS marriage_id, m.status, m.start_date, m.end_date,
       CASE WHEN m.husband_id = :person_id THEN m.wife_id ELSE m.husband_id END AS spouse_id
FROM marriage m
WHERE m.husband_id = :person_id OR m.wife_id = :person_id
ORDER BY COALESCE(m.end_date, '9999-12-31') DESC, m.id DESC
"""


@dataclass(frozen=True)
class RelationMatch:
    """A relative and how it is related."""

    person: Person
    relation: str
    code: str
    generation_diff: int
    path: list[int]


@dataclass(frozen=True)
class RelationshipResult:
    """Result of comparing two people."""

    relation: str | None
    code: str | None
    generations: int | None
    common_ancestor: Person | None
    path: list[int]
    distance: int
    relation_from_a: str | None
    relation_from_b: str | None
    explanation: str | None


class RelationshipService:
    """Family-relationship queries for a single database session."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _persons(self, ids: Iterable[int]) -> dict[int, Person]:
        unique = [i for i in dict.fromkeys(ids) if i is not None]
        if not unique:
            return {}
        rows = self.db.query(Person).filter(Person.id.in_(unique)).all()
        return {p.id: p for p in rows}

    def ancestor_map(self, person_id: int, max_depth: int = MAX_DEPTH) -> dict[int, int]:
        """``{ancestor_id: minimum generation distance}``."""
        rows = self.db.execute(
            text(_ANCESTORS_SQL), {"person_id": person_id, "max_depth": max_depth}
        )
        return {row[0]: int(row[1]) for row in rows}

    def descendant_map(self, person_id: int, max_depth: int = MAX_DEPTH) -> dict[int, int]:
        """``{descendant_id: minimum generation distance}``."""
        rows = self.db.execute(
            text(_DESCENDANTS_SQL), {"person_id": person_id, "max_depth": max_depth}
        )
        return {row[0]: int(row[1]) for row in rows}

    def _step_towards(
        self,
        person: Person,
        distance_map: dict[int, int],
        cache: dict[int, Person] | None = None,
        target_id: int | None = None,
    ) -> Person | None:
        """Return the parent that moves one step closer to the target.

        ``target_id`` disambiguates the last hop. When the target is exactly one
        generation above ``person`` both parents can share the same distance in
        ``distance_map`` (they lead to a common ancestor), and only one of them
        actually links to the target.
        """
        if (
            target_id is not None
            and distance_map.get(target_id) == distance_map.get(person.id, 0) + 1
        ):
            for parent_id in (person.father_id, person.mother_id):
                if parent_id == target_id:
                    if cache is not None and parent_id in cache:
                        return cache[parent_id]
                    parent = self.db.get(Person, parent_id)
                    if cache is not None and parent is not None:
                        cache[parent_id] = parent
                    return parent

        candidates: list[tuple[int, int]] = []
        if person.father_id and person.father_id in distance_map:
            candidates.append((distance_map[person.father_id], person.father_id))
        if person.mother_id and person.mother_id in distance_map:
            candidates.append((distance_map[person.mother_id], person.mother_id))
        if not candidates:
            return None
        candidates.sort()
        parent_id = candidates[0][1]
        if cache is not None and parent_id in cache:
            return cache[parent_id]
        parent = self.db.get(Person, parent_id)
        if cache is not None and parent is not None:
            cache[parent_id] = parent
        return parent

    # ------------------------------------------------------------------ #
    # Direct relationships
    # ------------------------------------------------------------------ #
    def parents(self, person: Person) -> dict[str, Any]:
        """Father, mother and the list of missing parent links."""
        father = self.db.get(Person, person.father_id) if person.father_id else None
        mother = self.db.get(Person, person.mother_id) if person.mother_id else None
        missing = []
        if father is None:
            missing.append("الأب")
        if mother is None:
            missing.append("الأم")
        return {"person_id": person.id, "father": father, "mother": mother, "missing": missing}

    def children(self, person: Person) -> dict[str, Any]:
        """Children split by the parent link they use."""
        rows = (
            self.db.query(Person)
            .filter(Person.father_id == person.id, Person.merged_into_id.is_(None))
            .order_by(Person.birth_date.is_(None), Person.birth_date, Person.id)
            .all()
        )
        as_father = list(rows)
        rows_m = (
            self.db.query(Person)
            .filter(Person.mother_id == person.id, Person.merged_into_id.is_(None))
            .order_by(Person.birth_date.is_(None), Person.birth_date, Person.id)
            .all()
        )
        as_mother = [p for p in rows_m if p.id not in {c.id for c in as_father}]
        return {
            "person_id": person.id,
            "as_father": as_father,
            "as_mother": as_mother,
            "total": len(as_father) + len(as_mother),
        }

    def siblings(self, person: Person) -> dict[str, Any]:
        """Full and half siblings."""
        rows = self.db.execute(text(_SIBLINGS_SQL), {"person_id": person.id}).all()
        persons = self._persons([row[0] for row in rows])
        full, half_paternal, half_maternal = [], [], []
        for sibling_id, same_father, same_mother in rows:
            sibling = persons.get(sibling_id)
            if sibling is None:
                continue
            item = {
                "person": sibling,
                "same_father": bool(same_father),
                "same_mother": bool(same_mother),
                "relation": self._sibling_label(sibling.gender, same_father, same_mother),
            }
            if same_father and same_mother:
                full.append(item)
            elif same_father:
                half_paternal.append(item)
            elif same_mother:
                half_maternal.append(item)
        return {
            "person_id": person.id,
            "full": full,
            "half_paternal": half_paternal,
            "half_maternal": half_maternal,
            "total": len(full) + len(half_paternal) + len(half_maternal),
        }

    def spouses(self, person: Person) -> list[dict[str, Any]]:
        """Every marriage record involving the person."""
        rows = self.db.execute(text(_SPOUSES_SQL), {"person_id": person.id}).all()
        persons = self._persons([row[4] for row in rows])
        result = []
        for marriage_id, status, start, end, spouse_id in rows:
            spouse = persons.get(spouse_id)
            if spouse is None:
                continue
            result.append(
                {
                    "person": spouse,
                    "marriage_id": marriage_id,
                    "status": status,
                    "start_date": start,
                    "end_date": end,
                    "relation": "زوج" if spouse.gender == "M" else "زوجة",
                }
            )
        return result

    # ------------------------------------------------------------------ #
    # Generations
    # ------------------------------------------------------------------ #
    def ancestors(self, person: Person, depth: int = 5) -> list[RelationMatch]:
        """Ancestors up to ``depth`` generations, ordered by distance."""
        depth = max(1, min(depth, MAX_DEPTH))
        distance_map = self.ancestor_map(person.id, depth)
        persons = self._persons(distance_map.keys())
        persons.setdefault(person.id, person)
        matches = []
        for ancestor_id, generation in sorted(distance_map.items(), key=lambda kv: (kv[1], kv[0])):
            ancestor = persons.get(ancestor_id)
            if ancestor is None:
                continue
            matches.append(
                RelationMatch(
                    person=ancestor,
                    relation=self._ancestor_label(generation, ancestor.gender),
                    code=f"parent_{generation}_{ancestor.gender or 'x'}",
                    generation_diff=-generation,
                    path=self._path_up(person, ancestor_id, distance_map, persons),
                )
            )
        return matches

    def descendants(self, person: Person, depth: int = 5) -> list[RelationMatch]:
        """Descendants up to ``depth`` generations, ordered by distance."""
        depth = max(1, min(depth, MAX_DEPTH))
        distance_map = self.descendant_map(person.id, depth)
        persons = self._persons(distance_map.keys())
        persons.setdefault(person.id, person)
        matches = []
        for descendant_id, generation in sorted(
            distance_map.items(), key=lambda kv: (kv[1], kv[0])
        ):
            descendant = persons.get(descendant_id)
            if descendant is None:
                continue
            matches.append(
                RelationMatch(
                    person=descendant,
                    relation=self._descendant_label(generation, descendant.gender),
                    code=f"child_{generation}_{descendant.gender or 'x'}",
                    generation_diff=generation,
                    path=self._path_down(person, descendant_id, distance_map, persons),
                )
            )
        return matches

    @staticmethod
    def _ancestor_label(generation: int, gender: str | None) -> str:
        """Label for an ancestor; ``gender`` is the ancestor's own gender."""
        return labels.lineal_ancestor_label(generation, gender)

    @staticmethod
    def _descendant_label(generation: int, gender: str | None) -> str:
        """Label for a descendant; ``gender`` is the descendant's own gender."""
        return labels.lineal_descendant_label(generation, gender)

    def _path_up(
        self,
        person: Person,
        target_id: int,
        distance_map: dict[int, int],
        cache: dict[int, Person] | None = None,
    ) -> list[int]:
        """Ids from ``person`` up to ``target_id`` inclusive.

        Falls back to ``[person.id]`` when the target is unreachable, which
        happens when the caller only supplied a truncated distance map.
        """
        if person.id == target_id:
            return [person.id]
        cache = cache if cache is not None else {}
        path = [person.id]
        current = person
        for _ in range(MAX_DEPTH):
            if current.id == target_id:
                return path
            nxt = self._step_towards(current, distance_map, cache, target_id)
            if nxt is None or nxt.id == current.id:
                break
            path.append(nxt.id)
            current = nxt
        return path if path[-1] == target_id else [person.id]

    def _path_down(
        self,
        person: Person,
        target_id: int,
        distance_map: dict[int, int],
        cache: dict[int, Person] | None = None,
    ) -> list[int]:
        """Ids from ``person`` down to ``target_id`` inclusive."""
        if person.id == target_id:
            return [person.id]
        # Walk up from the descendant using the ancestor distances, then reverse.
        reverse = self._path_up(self._require(target_id), person.id, distance_map, cache)
        if not reverse or reverse[-1] != person.id:
            return [person.id]
        return list(reversed(reverse))

    def _require(self, person_id: int) -> Person:
        person = self.db.get(Person, person_id)
        if person is None:
            from app.core.exceptions import NotFoundError

            raise NotFoundError(Messages.PERSON_NOT_FOUND)
        return person

    # ------------------------------------------------------------------ #
    # Tree
    # ------------------------------------------------------------------ #
    def tree(
        self, person: Person, up: int = 3, down: int = 4, max_nodes: int = 4000
    ) -> dict[str, Any]:
        """Nodes and links ready for the front-end chart.

        ``up`` generations of parents and ``down`` generations of children are
        included, plus the missing spouse of every included couple so the
        chart has no dangling parent links.
        """
        up = max(0, min(up, MAX_DEPTH))
        down = max(0, min(down, MAX_DEPTH))

        nodes: dict[int, dict[str, Any]] = {}
        links: list[dict[str, Any]] = []
        edge_keys: set[tuple[int, int]] = set()
        rows: dict[int, Person] = {}

        def load(person_id: int) -> Person | None:
            if person_id in rows:
                return rows[person_id]
            row = self.db.get(Person, person_id)
            if row is not None:
                rows[person_id] = row
            return row

        def ensure(person_id: int, depth: int) -> dict[str, Any] | None:
            row = load(person_id)
            if row is None:
                return None
            if person_id not in nodes:
                if len(nodes) >= max_nodes:
                    return None
                nodes[person_id] = {
                    "id": person_id,
                    "depth": depth,
                    "generation": self._generation_label(depth),
                    "children": [],
                    "has_more_parents": bool(row.father_id or row.mother_id),
                    "has_more_children": False,
                }
            return nodes[person_id]

        def link(parent_id: int, child_id: int) -> None:
            key = (parent_id, child_id)
            if key in edge_keys:
                return
            edge_keys.add(key)
            links.append({"source": parent_id, "target": child_id, "kind": "parent"})
            child = nodes.get(child_id)
            if child is not None and parent_id not in child["children"]:
                child["children"].append(parent_id)

        root = ensure(person.id, 0)
        assert root is not None

        # ---- upward: BFS over parents -----------------------------------
        frontier: deque[tuple[int, int]] = deque([(person.id, 0)])
        visited: set[int] = {person.id}
        while frontier:
            node_id, depth = frontier.popleft()
            if -depth >= up:
                row = load(node_id)
                nodes[node_id]["has_more_parents"] = bool(row and (row.father_id or row.mother_id))
                continue
            row = load(node_id)
            if row is None:
                continue
            for parent_id in (row.father_id, row.mother_id):
                if not parent_id or parent_id in visited:
                    continue
                if ensure(parent_id, depth - 1) is None:
                    nodes[node_id]["has_more_parents"] = True
                    break
                visited.add(parent_id)
                link(parent_id, node_id)
                frontier.append((parent_id, depth - 1))

        # ---- downward: BFS over children --------------------------------
        frontier = deque([(person.id, 0)])
        visited = {person.id}
        while frontier:
            node_id, depth = frontier.popleft()
            if depth >= down:
                continue
            rows_out = self.db.execute(
                text(
                    """
                    SELECT id FROM person
                    WHERE (father_id = :pid OR mother_id = :pid)
                      AND merged_into_id IS NULL
                    ORDER BY COALESCE(birth_date, DATE '9999-12-31'), id
                    LIMIT :limit
                    """
                ),
                {"pid": node_id, "limit": max_nodes},
            ).fetchall()
            for (child_id,) in rows_out:
                if child_id in visited:
                    continue
                if ensure(child_id, depth + 1) is None:
                    nodes[node_id]["has_more_children"] = True
                    break
                visited.add(child_id)
                # Link from whichever parent is already part of the tree.
                child_row = load(child_id)
                for parent_id in (child_row.father_id, child_row.mother_id):
                    if parent_id in nodes:
                        link(parent_id, child_id)
                frontier.append((child_id, depth + 1))

        # ---- complete couples: add a missing parent of an included person
        for node_id in list(nodes):
            row = load(node_id)
            if row is None:
                continue
            depth = nodes[node_id]["depth"]
            for parent_id in (row.father_id, row.mother_id):
                if (
                    parent_id
                    and parent_id not in nodes
                    and ensure(parent_id, depth - 1) is not None
                ):
                    link(parent_id, node_id)

        # ---- spouse links -------------------------------------------------
        marriages = self._marriages_for_nodes(nodes.keys())
        for marriage in marriages:
            key = (marriage["husband_id"], marriage["wife_id"])
            if key not in edge_keys:
                links.append(
                    {
                        "source": marriage["husband_id"],
                        "target": marriage["wife_id"],
                        "kind": "spouse",
                    }
                )

        # ---- hydrate node payloads ----------------------------------------
        node_list: list[dict[str, Any]] = []
        for node in sorted(nodes.values(), key=lambda n: (n["depth"], n["id"])):
            row = load(node["id"])
            if row is None:
                continue
            node.update(
                {
                    "full_name": row.full_name,
                    "gender": row.gender,
                    "birth_date": row.birth_date,
                    "death_date": row.death_date,
                    "birth_place": row.birth_place,
                    "father_id": row.father_id,
                    "mother_id": row.mother_id,
                }
            )
            node_list.append(node)

        return {
            "person_id": person.id,
            "up": up,
            "down": down,
            "nodes": node_list,
            "links": links,
            "marriages": marriages,
            "total_nodes": len(node_list),
            "truncated": len(node_list) >= max_nodes,
        }

    @staticmethod
    def _generation_label(depth: int) -> str:
        if depth == 0:
            return "الأنفس"
        if depth == -1:
            return "الأب / الأم"
        if depth == -2:
            return "الجد / الجدة"
        if depth < 0:
            return f"الجد من الدرجة {abs(depth)}"
        if depth == 1:
            return "الأبناء"
        if depth == 2:
            return "الأحفاد"
        return f"الجيل {depth + 1}"

    def _marriages_for_nodes(self, node_ids: Iterable[int]) -> list[dict[str, Any]]:
        ids = list(node_ids)
        if not ids:
            return []
        rows = (
            self.db.execute(
                text(
                    """
                SELECT id, husband_id, wife_id, start_date, end_date, status
                FROM marriage
                WHERE husband_id = ANY(CAST(:ids AS BIGINT[]))
                   OR wife_id = ANY(CAST(:ids AS BIGINT[]))
                """
                ),
                {"ids": ids},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Extended relatives
    # ------------------------------------------------------------------ #
    def relatives(self, person: Person) -> dict[str, list[RelationMatch]]:
        """Uncles/aunts, cousins, nephews/nieces and in-laws."""
        results: dict[str, list[RelationMatch]] = {
            "uncles_aunts": [],
            "cousins": [],
            "nephews_nieces": [],
            "in_laws": [],
            "grand_uncles": [],
            "grand_aunts": [],
        }
        seen: set[tuple[str, int]] = set()

        def add(bucket: str, match: RelationMatch) -> None:
            key = (bucket, match.person.id)
            if key not in seen:
                seen.add(key)
                results[bucket].append(match)

        ancestors = self.ancestors(person, depth=4)

        # --- Uncles / aunts: siblings of my parents and grandparents -------
        for ancestor in ancestors[:6]:  # parents and grandparents
            generation = abs(ancestor.generation_diff)
            if generation > 3:
                continue
            for sibling in self._siblings_of(ancestor.person):
                bucket = {
                    1: "uncles_aunts",
                    2: "uncles_aunts",
                    3: "grand_uncles",
                }.get(generation, "grand_uncles")
                if sibling["person"].id == person.id:
                    continue
                add(
                    bucket,
                    RelationMatch(
                        person=sibling["person"],
                        relation=labels.label_for_person(
                            labels.UNCLE, gender=sibling["person"].gender
                        ),
                        code=labels.UNCLE,
                        generation_diff=-generation,
                        path=[person.id, ancestor.person.id, sibling["person"].id],
                    ),
                )
                # Grand-aunt: a great-grandparent's sibling.
                if generation >= 2:
                    add(
                        "grand_aunts",
                        RelationMatch(
                            person=sibling["person"],
                            relation=labels.label_for_person(
                                labels.GRAND_AUNT, gender=sibling["person"].gender
                            ),
                            code=labels.GRAND_AUNT,
                            generation_diff=-generation,
                            path=[person.id, ancestor.person.id, sibling["person"].id],
                        ),
                    )

        # --- Cousins: children of my uncles/aunts ---------------------------
        for ancestor in ancestors[:4]:
            for sibling in self._siblings_of(ancestor.person):
                if sibling["person"].id == person.id:
                    continue
                cousin_bucket = "cousins" if abs(ancestor.generation_diff) <= 1 else "cousins"
                sib_children = self.children(sibling["person"])
                for child in sib_children["as_father"] + sib_children["as_mother"]:
                    if child.id == person.id:
                        continue
                    degree = 1 if abs(ancestor.generation_diff) == 1 else 2
                    code = labels.COUSIN_M if degree == 1 else labels.SECOND_COUSIN_M
                    add(
                        cousin_bucket,
                        RelationMatch(
                            person=child,
                            relation=labels.label_for_person(code, gender=child.gender),
                            code=code,
                            generation_diff=0,
                            path=[person.id, ancestor.person.id, sibling["person"].id, child.id],
                        ),
                    )

        # --- Nephews / nieces: children of my siblings ----------------------
        for sibling in self._siblings_of(person):
            sib_children = self.children(sibling["person"])
            for child in sib_children["as_father"] + sib_children["as_mother"]:
                add(
                    "nephews_nieces",
                    RelationMatch(
                        person=child,
                        relation=labels.label_for_person(labels.NEPHEW, gender=child.gender),
                        code=labels.NEPHEW,
                        generation_diff=-1,
                        path=[person.id, sibling["person"].id, child.id],
                    ),
                )
                # Grand nephews/nieces: children of those nephews.
                for grand_child in self._children_of_any(child):
                    add(
                        "nephews_nieces",
                        RelationMatch(
                            person=grand_child,
                            relation=labels.label_for_person(
                                labels.GRAND_NEPHEW, gender=grand_child.gender
                            ),
                            code=labels.GRAND_NEPHEW,
                            generation_diff=-2,
                            path=[person.id, sibling["person"].id, child.id, grand_child.id],
                        ),
                    )

        # --- In-laws ---------------------------------------------------------
        for spouse in self.spouses(person):
            spouse_map = self.ancestor_map(spouse["person"].id, 4)
            for ancestor_id, generation in spouse_map.items():
                if generation not in (1, 2):
                    continue
                ancestor = self.db.get(Person, ancestor_id)
                if ancestor is None:
                    continue
                code = labels.FATHER_IN_LAW if ancestor.gender == "M" else labels.MOTHER_IN_LAW
                add(
                    "in_laws",
                    RelationMatch(
                        person=ancestor,
                        relation=labels.ARABIC_LABELS[code],
                        code=code,
                        generation_diff=-generation,
                        path=[person.id, spouse["person"].id, ancestor_id],
                    ),
                )
            spouse_children = self.children(spouse["person"])
            my_children = self.children(person)
            shared = {c.id for c in my_children["as_father"] + my_children["as_mother"]}
            for child in spouse_children["as_father"] + spouse_children["as_mother"]:
                # Children shared with the subject are his own, not in-laws.
                if child.id in shared:
                    continue
                code = labels.SON_IN_LAW if child.gender == "M" else labels.DAUGHTER_IN_LAW
                add(
                    "in_laws",
                    RelationMatch(
                        person=child,
                        relation=labels.ARABIC_LABELS[code],
                        code=code,
                        generation_diff=1,
                        path=[person.id, spouse["person"].id, child.id],
                    ),
                )
            for sibling in self._siblings_of(spouse["person"]):
                code = (
                    labels.BROTHER_IN_LAW
                    if sibling["person"].gender == "M"
                    else labels.SISTER_IN_LAW
                )
                add(
                    "in_laws",
                    RelationMatch(
                        person=sibling["person"],
                        relation=labels.ARABIC_LABELS[code],
                        code=code,
                        generation_diff=0,
                        path=[person.id, spouse["person"].id, sibling["person"].id],
                    ),
                )

        for bucket in results:
            results[bucket].sort(key=lambda m: (m.person.full_name, m.person.id))
        return results

    def _children_of_any(self, person: Person) -> list[Person]:
        return self.children(person)["as_father"] + self.children(person)["as_mother"]

    @staticmethod
    def _sibling_label(gender: str | None, same_father: bool, same_mother: bool) -> str:
        """Arabic sibling word: أخ/أخت for full, نصف phrasing otherwise."""
        if same_father and same_mother:
            code = labels.BROTHER if gender == "M" else labels.SISTER
        else:
            code = labels.HALF_BROTHER if gender == "M" else labels.HALF_SISTER
        return labels.ARABIC_LABELS[code]

    def _siblings_of(self, person: Person) -> list[dict[str, Any]]:
        """Sibling dicts for an arbitrary person (not necessarily the subject)."""
        data = self.siblings(person)
        return [
            item for bucket in ("full", "half_paternal", "half_maternal") for item in data[bucket]
        ]

    # ------------------------------------------------------------------ #
    # Relationship finder
    # ------------------------------------------------------------------ #
    def relationship(self, a_id: int, b_id: int) -> RelationshipResult:
        """Describe how ``a`` relates to ``b`` and return the shortest path."""
        person_a = self._require(a_id)
        person_b = self._require(b_id)

        if a_id == b_id:
            return RelationshipResult(
                relation=labels.ARABIC_LABELS[labels.SELF],
                code=labels.SELF,
                generations=0,
                common_ancestor=None,
                path=[a_id],
                distance=0,
                relation_from_a=None,
                relation_from_b=None,
                explanation="نفس الشخص",
            )

        map_a = self.ancestor_map(a_id, MAX_DEPTH)
        map_b = self.ancestor_map(b_id, MAX_DEPTH)

        # --- Direct line -----------------------------------------------------
        if b_id in map_a:
            generation = map_a[b_id]
            return self._direct_line(
                a_id, b_id, generation, "descendant", person_a, person_b, map_a
            )
        if a_id in map_b:
            generation = map_b[a_id]
            return self._direct_line(a_id, b_id, generation, "ancestor", person_a, person_b, map_b)

        # --- Collateral: find the closest common ancestor --------------------
        common = set(map_a) & set(map_b)
        if common:
            lca_id = min(
                common, key=lambda cid: (map_a[cid] + map_b[cid], max(map_a[cid], map_b[cid]), cid)
            )
            lca = self.db.get(Person, lca_id)
            # eA/eB = generations between each person and the branch head below the LCA.
            e_a = max(0, map_a[lca_id] - 1)
            e_b = max(0, map_b[lca_id] - 1)
            result = self._collateral(a_id, b_id, e_a, e_b, person_a, person_b, map_a, map_b, lca)
            if result is not None:
                return result

        # --- In-laws --------------------------------------------------------
        spousal = self._marital_relation(a_id, b_id, person_a, person_b)
        if spousal is not None:
            return spousal

        return RelationshipResult(
            relation=None,
            code=None,
            generations=None,
            common_ancestor=None,
            path=[],
            distance=-1,
            relation_from_a=None,
            relation_from_b=None,
            explanation="لا توجد علاقة قرابة معروفة بين الشخصين",
        )

    def _direct_line(
        self,
        a_id: int,
        b_id: int,
        generation: int,
        direction: str,
        person_a: Person,
        person_b: Person,
        distance_map: dict[int, int],
    ) -> RelationshipResult:
        """One person is a direct ancestor of the other.

        ``direction`` names which side is above: ``"ancestor"`` means A is the
        ancestor of B, anything else means B is the ancestor of A.

        The response contract is symmetric and independent of the query order:
        ``relation`` names the senior's role ("محمد is Nour's grandfather"),
        ``relation_from_a`` / ``relation_from_b`` each describe one person's
        role in the pair, and ``generations`` is positive when A is above B.
        """
        if direction == "ancestor":  # a is above b
            senior, junior = person_a, person_b
            relation_from_a = self._ancestor_label(generation, person_a.gender)
            relation_from_b = self._descendant_label(generation, person_b.gender)
            generations = generation
            path = self._path_up(person_b, a_id, distance_map)
        else:  # b is above a
            senior, junior = person_b, person_a
            relation_from_a = self._descendant_label(generation, person_a.gender)
            relation_from_b = self._ancestor_label(generation, person_b.gender)
            generations = -generation
            path = self._path_up(person_a, b_id, distance_map)

        relation = self._ancestor_label(generation, senior.gender)
        explanation = labels.relation_sentence(
            senior.full_name, senior.gender, relation, junior.full_name
        )
        return RelationshipResult(
            relation=relation,
            code=self._descendant_code(generation, junior.gender),
            generations=generations,
            common_ancestor=self.db.get(Person, senior.id),
            path=path,
            distance=generation,
            relation_from_a=relation_from_a,
            relation_from_b=relation_from_b,
            explanation=explanation,
        )

    @staticmethod
    def _descendant_code(generation: int, gender: str | None) -> str:
        if generation == 1:
            return labels.CHILD_M if gender == "M" else labels.CHILD_F
        if generation == 2:
            return labels.GRANDCHILD_M if gender == "M" else labels.GRANDCHILD_F
        return labels.GREAT_GRANDCHILD_M if gender == "M" else labels.GREAT_GRANDCHILD_F

    @staticmethod
    def _ancestor_code(generation: int, gender: str | None) -> str:
        if generation == 1:
            return labels.PARENT_M if gender == "M" else labels.PARENT_F
        if generation == 2:
            return labels.GRANDPARENT_M if gender == "M" else labels.GRANDPARENT_F
        return labels.GREAT_GRANDPARENT_M if gender == "M" else labels.GREAT_GRANDPARENT_F

    def _collateral(
        self,
        a_id: int,
        b_id: int,
        e_a: int,
        e_b: int,
        person_a: Person,
        person_b: Person,
        map_a: dict[int, int],
        map_b: dict[int, int],
        lca: Person | None,
    ) -> RelationshipResult | None:
        """Both people descend from siblings of the closest common ancestor."""
        common_ids = set(map_a) & set(map_b)
        lca_id = min(
            common_ids, key=lambda cid: (map_a[cid] + map_b[cid], max(map_a[cid], map_b[cid]), cid)
        )

        # Half-sibling check when they share the same branch head (e_a == e_b == 0).
        if e_a == 0 and e_b == 0:
            same_father = (
                person_a.father_id is not None and person_a.father_id == person_b.father_id
            )
            same_mother = (
                person_a.mother_id is not None and person_a.mother_id == person_b.mother_id
            )
            if same_father and same_mother:
                code = labels.BROTHER if person_b.gender == "M" else labels.SISTER
                relation = labels.ARABIC_LABELS[code]
            else:
                code = labels.HALF_BROTHER if person_b.gender == "M" else labels.HALF_SISTER
                relation = labels.ARABIC_LABELS[code]
            path = [a_id, lca_id, b_id]
            return RelationshipResult(
                relation=relation,
                code=code,
                generations=0,
                common_ancestor=lca,
                path=path,
                distance=2,
                relation_from_a="أخوة",
                relation_from_b=relation,
                explanation=f"{person_a.full_name} و {person_b.full_name} إخوة",
            )

        # One of them is an ancestor of the other's branch head.
        # ``relation`` names the senior side of the pair (the uncle/aunt),
        # ``relation_from_b`` names the junior side (nephew/niece).
        if e_a == 0 or e_b == 0:
            ancestor_side = "a" if e_a == 0 else "b"
            degree = e_b if e_a == 0 else e_a
            if ancestor_side == "a":
                # A is the uncle/aunt of B: the branch runs through B.
                paternal = self._branch_is_paternal(person_b, lca_id, map_b)
                code = labels.uncle_code(degree, paternal=paternal, gender=person_a.gender)
                relation = labels.ARABIC_LABELS[code]
                nephew = labels.nephew_code(degree, paternal=paternal, gender=person_b.gender)
                path = [a_id, lca_id]
                generations = -max(map_a[lca_id] - 1, 1)
                return RelationshipResult(
                    relation=relation,
                    code=code,
                    generations=generations,
                    common_ancestor=lca,
                    path=path + self._path_down_from(lca_id, b_id, map_b),
                    distance=max(map_a[lca_id] - 1, 1) + map_b[lca_id],
                    relation_from_a=relation,
                    relation_from_b=labels.ARABIC_LABELS[nephew],
                    explanation=f"{person_a.full_name} {relation} {person_b.full_name}",
                )
            # B is the uncle/aunt of A: the branch runs through A.
            paternal = self._branch_is_paternal(person_a, lca_id, map_a)
            code = labels.uncle_code(degree, paternal=paternal, gender=person_b.gender)
            relation = labels.ARABIC_LABELS[code]
            nephew = labels.nephew_code(degree, paternal=paternal, gender=person_a.gender)
            return RelationshipResult(
                relation=relation,
                code=code,
                generations=max(map_b[lca_id] - 1, 1),
                common_ancestor=lca,
                path=[*self._path_up(person_a, lca_id, map_a), b_id],
                distance=max(map_b[lca_id] - 1, 1) + map_a[lca_id],
                relation_from_a=labels.ARABIC_LABELS[nephew],
                relation_from_b=relation,
                explanation=f"{person_b.full_name} {relation} {person_a.full_name}",
            )

        # Cousins (possibly removed).
        degree = min(e_a, e_b)
        removed = abs(e_a - e_b)
        if degree == 1 and removed == 0:
            base = labels.COUSIN_M if person_b.gender == "M" else labels.COUSIN_F
        elif degree == 2 and removed == 0:
            base = labels.SECOND_COUSIN_M if person_b.gender == "M" else labels.SECOND_COUSIN_F
        else:
            base = labels.COUSIN_M if person_b.gender == "M" else labels.COUSIN_F
        relation = labels.label_for_person(base, gender=person_b.gender)
        if removed:
            relation = f"{relation} (مزالة {removed} درجة)"
        elif degree >= 3:
            relation = f"{relation} من الدرجة {degree}"

        return RelationshipResult(
            relation=relation,
            code=base,
            generations=0,
            common_ancestor=lca,
            path=[a_id, lca_id, b_id],
            distance=e_a + e_b + 2,
            relation_from_a=relation,
            relation_from_b=relation,
            explanation=f"{person_a.full_name} {relation} {person_b.full_name}",
        )

    def _branch_is_paternal(
        self, person: Person, lca_id: int, distance_map: dict[int, int]
    ) -> bool:
        """True when ``person``'s branch descends from the LCA through his father.

        Arabic kinship distinguishes عم/عة (paternal) from خال/خالة (maternal),
        so the link that leaves the common ancestor has to be resolved: walk up
        ``person`` until reaching a sibling of the LCA and inspect that link.
        ``distance_map`` is measured from ``person``, so the child of the LCA
        sits one generation closer to it. Falls back to the paternal reading
        when the branch cannot be resolved.
        """
        lca_depth = distance_map.get(lca_id)
        if lca_depth is None:
            return True
        # Breadth-first over parents recorded in the map, so a parent with no
        # recorded ancestry can never be mistaken for the branch that leads to
        # the common ancestor.
        frontier = [person]
        seen = {person.id}
        for _ in range(MAX_DEPTH):
            following: list[Person] = []
            for node in frontier:
                depth = distance_map.get(node.id, 0)
                for parent_id in (node.father_id, node.mother_id):
                    if (
                        parent_id is None
                        or parent_id in seen
                        or distance_map.get(parent_id) != depth + 1
                    ):
                        continue
                    if parent_id == lca_id:
                        return node.father_id == lca_id
                    parent = self.db.get(Person, parent_id)
                    if parent is not None:
                        following.append(parent)
            frontier = following
            seen.update(node.id for node in frontier)
        return True

    def _path_down_from(
        self, ancestor_id: int, target_id: int, distance_map: dict[int, int]
    ) -> list[int]:
        """Ids from ``ancestor_id`` (exclusive) down to ``target_id``."""
        reverse = self._path_up(self._require(target_id), ancestor_id, distance_map)
        return list(reversed(reverse))

    def _marital_relation(
        self, a_id: int, b_id: int, person_a: Person, person_b: Person
    ) -> RelationshipResult | None:
        """Spouses and in-laws when there is no blood link."""
        spouses_b = {s["person"].id: s for s in self.spouses(person_b)}
        if a_id in spouses_b:
            relation = "زوج" if person_a.gender == "M" else "زوجة"
            return RelationshipResult(
                relation=relation,
                code="spouse",
                generations=0,
                common_ancestor=None,
                path=[a_id, b_id],
                distance=1,
                relation_from_a=relation,
                relation_from_b=relation,
                explanation=f"{person_a.full_name} {relation} {person_b.full_name}",
            )

        spouses_a = {s["person"].id: s for s in self.spouses(person_a)}
        if b_id in spouses_a:
            relation = "زوج" if person_b.gender == "M" else "زوجة"
            return RelationshipResult(
                relation=relation,
                code="spouse",
                generations=0,
                common_ancestor=None,
                path=[a_id, b_id],
                distance=1,
                relation_from_a=relation,
                relation_from_b=relation,
                explanation=f"{person_a.full_name} {relation} {person_b.full_name}",
            )

        # A is the parent of B's spouse (or vice versa) -> in-law.
        b_map = self.ancestor_map(b_id, 3)
        for spouse_entry in self.spouses(person_a):
            spouse_id = spouse_entry["person"].id
            if spouse_id in b_map and b_map[spouse_id] <= 3:
                generation = b_map[spouse_id]
                spouse_person = spouse_entry["person"]
                if generation == 1:
                    code = labels.SON_IN_LAW if person_b.gender == "M" else labels.DAUGHTER_IN_LAW
                else:
                    code = labels.COUSIN_IN_LAW
                return RelationshipResult(
                    relation=labels.ARABIC_LABELS[code],
                    code=code,
                    generations=0,
                    common_ancestor=None,
                    path=[a_id, spouse_id, b_id],
                    distance=generation + 1,
                    relation_from_a=labels.ARABIC_LABELS[code],
                    relation_from_b=labels.ARABIC_LABELS[code],
                    explanation=labels.relation_sentence(
                        person_b.full_name,
                        person_b.gender,
                        "زوجة" if person_b.gender == "M" else "زوج",
                        spouse_person.full_name,
                    ),
                )

        a_map = self.ancestor_map(a_id, 3)
        for spouse_entry in self.spouses(person_b):
            spouse_id = spouse_entry["person"].id
            if spouse_id in a_map and a_map[spouse_id] <= 3:
                generation = a_map[spouse_id]
                if generation == 1:
                    code = labels.FATHER_IN_LAW if person_b.gender == "M" else labels.MOTHER_IN_LAW
                else:
                    code = labels.UNCLE_IN_LAW
                return RelationshipResult(
                    relation=labels.ARABIC_LABELS[code],
                    code=code,
                    generations=0,
                    common_ancestor=None,
                    path=[a_id, spouse_id, b_id],
                    distance=generation + 1,
                    relation_from_a=labels.ARABIC_LABELS[code],
                    relation_from_b=labels.ARABIC_LABELS[code],
                    explanation=labels.relation_sentence(
                        person_b.full_name,
                        person_b.gender,
                        "صهر" if person_b.gender == "M" else "صهلة",
                        person_a.full_name,
                    ),
                )

        return None
