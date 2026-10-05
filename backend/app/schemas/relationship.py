"""Pydantic schemas for relationship endpoints."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.person import PersonOut, PersonRef


class RelativeItem(PersonRef):
    """A relative with the Arabic label describing the link."""

    relation: str = Field(..., description="علاقة القرابة بالعربية")
    relation_code: str = Field(..., description="رمز العلاقة بالإنجليزية")
    generation_diff: int = Field(..., description="فرق الأجيال (موجب = أب_generation)")
    path: list[int] = Field(default_factory=list, description="المسار من الشخص المطلوب")


class ParentsResponse(BaseModel):
    """``/persons/{id}/parents``."""

    person_id: int
    father: PersonOut | None = None
    mother: PersonOut | None = None
    missing: list[str] = Field(default_factory=list, description="الوالدان غير المسجلين")


class ChildrenResponse(BaseModel):
    """``/persons/{id}/children``."""

    person_id: int
    as_father: list[PersonRef] = Field(default_factory=list)
    as_mother: list[PersonRef] = Field(default_factory=list)
    total: int = 0


class SiblingItem(PersonRef):
    """A sibling with full/half classification."""

    relation: str
    sibling_type: Literal["full", "half_paternal", "half_maternal"]


class SiblingsResponse(BaseModel):
    """``/persons/{id}/siblings``."""

    person_id: int
    full: list[SiblingItem] = Field(default_factory=list)
    half_paternal: list[SiblingItem] = Field(default_factory=list)
    half_maternal: list[SiblingItem] = Field(default_factory=list)
    total: int = 0


class SpouseItem(PersonRef):
    """A spouse."""

    marriage_id: int
    status: str
    start_date: str | None = None
    end_date: str | None = None
    relation: str = "زوج/ة"


class SpousesResponse(BaseModel):
    """``/persons/{id}/spouses``."""

    person_id: int
    spouses: list[SpouseItem] = Field(default_factory=list)
    total: int = 0


class AncestorItem(PersonRef):
    """One ancestor with its generation distance."""

    generation: int = Field(..., description="المسافة: 1 = الأب/الأم، 2 = الجد/الجدة")
    generation_label: str
    relation: str


class AncestorsResponse(BaseModel):
    """``/persons/{id}/ancestors?depth=N``."""

    person_id: int
    depth: int
    ancestors: list[AncestorItem] = Field(default_factory=list)
    max_generation_found: int = 0
    total: int = 0


class DescendantItem(PersonRef):
    """One descendant with its generation distance."""

    generation: int = Field(..., description="المسافة: 1 = الابن/الابنة")
    generation_label: str
    relation: str


class DescendantsResponse(BaseModel):
    """``/persons/{id}/descendants?depth=N``."""

    person_id: int
    depth: int
    descendants: list[DescendantItem] = Field(default_factory=list)
    max_generation_found: int = 0
    total: int = 0


class TreeNode(PersonRef):
    """A node in the tree payload."""

    depth: int = Field(..., description="0 = جذر الشجرة، سالب = للأعلى")
    generation: str = Field(..., description="تسجيل عربي: الأب، الجد، الجد الأب ...")
    children: list[int] = Field(default_factory=list)
    has_more_parents: bool = False
    has_more_children: bool = False


class TreeLink(BaseModel):
    """An edge in the tree payload."""

    source: int
    target: int
    kind: Literal["parent", "spouse"] = "parent"


class TreeMarriage(BaseModel):
    """A marriage edge included in the tree payload."""

    id: int
    husband_id: int
    wife_id: int
    start_date: date | None = None
    end_date: date | None = None
    status: str | None = None


class TreeResponse(BaseModel):
    """``/persons/{id}/tree?up=N&down=N``."""

    person_id: int
    up: int
    down: int
    nodes: list[TreeNode]
    links: list[TreeLink]
    marriages: list[TreeMarriage] = Field(default_factory=list)
    total_nodes: int = 0
    truncated: bool = False


class RelationshipPathStep(BaseModel):
    """One hop in the shortest relationship path."""

    person_id: int
    full_name: str
    role: str = Field(..., description="دور الشخص في المسار")
    relation_to_next: str | None = Field(default=None, description="نوع العلاقة مع الخطوة التالية")


class RelationshipResponse(BaseModel):
    """``/relationship?a=ID&b=ID``."""

    a: int
    b: int
    relation: str | None = Field(default=None, description="العلاقة بالعربية، مثال: ابن عم")
    relation_code: str | None = None
    generations: int | None = Field(default=None, description="فرق الأجيال بين الشخصين")
    common_ancestor_id: int | None = None
    common_ancestor_name: str | None = None
    path: list[RelationshipPathStep] = Field(default_factory=list)
    distance: int = 0
    relation_from_a: str | None = None
    relation_from_b: str | None = None
    explanation: str | None = None


class RelativesResponse(BaseModel):
    """``/persons/{id}/relatives``."""

    person_id: int
    uncles_aunts: list[RelativeItem] = Field(default_factory=list)
    cousins: list[RelativeItem] = Field(default_factory=list)
    nephews_nieces: list[RelativeItem] = Field(default_factory=list)
    in_laws: list[RelativeItem] = Field(default_factory=list)
    grand_uncles: list[RelativeItem] = Field(default_factory=list)
    grand_aunts: list[RelativeItem] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
