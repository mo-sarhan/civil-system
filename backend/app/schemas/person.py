"""Pydantic schemas for persons."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_core.core_schema import ValidationInfo

from app.utils.arabic import parse_full_name
from app.utils.messages import Messages
from app.utils.national_id import validate_national_id

Gender = Literal["M", "F"]

#: Arabic and English spellings accepted for the gender field.
_GENDER_ALIASES: dict[str, str] = {
    "m": "M",
    "male": "M",
    "ذكر": "M",
    "ذكرى": "M",
    "f": "F",
    "female": "F",
    "انثى": "F",
    "انثه": "F",
    "أنثى": "F",
    "بنت": "F",
    "ام": "F",
}


def _normalize_gender(value: Any) -> str | None:
    """Map any accepted gender spelling to ``'M'``/``'F'`` (or ``None``)."""
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"m", "f"}:
        return text.upper()
    if text in _GENDER_ALIASES:
        return _GENDER_ALIASES[text]
    raise ValueError(Messages.GENDER_INVALID)


PERSON_SORT_FIELDS = {
    "id": "id",
    "full_name": "full_name",
    "birth_date": "birth_date",
    "created_at": "created_at",
    "updated_at": "updated_at",
}


class PersonBase(BaseModel):
    """Fields accepted on create and update."""

    national_id: str | None = Field(default=None, max_length=14)
    full_name: str = Field(min_length=1, max_length=300)
    first_name: str | None = Field(default=None, max_length=100)
    father_name: str | None = Field(default=None, max_length=100)
    grandfather_name: str | None = Field(default=None, max_length=100)
    family_name: str | None = Field(default=None, max_length=100)
    gender: Gender | None = None
    birth_date: date | None = None
    death_date: date | None = None
    birth_place: str | None = Field(default=None, max_length=255)
    father_id: int | None = None
    mother_id: int | None = None
    notes: str | None = None

    @field_validator("full_name")
    @classmethod
    def _name_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError(Messages.FULL_NAME_REQUIRED)
        return value

    @field_validator("gender", mode="before")
    @classmethod
    def _gender_normalize(cls, value: Any) -> str | None:
        return _normalize_gender(value)

    @field_validator("birth_date", "death_date")
    @classmethod
    def _not_future(cls, value: date | None, info: ValidationInfo) -> date | None:
        if value is not None and value > date.today():
            message = (
                Messages.BIRTH_IN_FUTURE
                if info.field_name == "birth_date"
                else Messages.DEATH_IN_FUTURE
            )
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def _check_dates(self) -> PersonBase:
        if self.birth_date and self.death_date and self.death_date < self.birth_date:
            raise ValueError(Messages.DEATH_BEFORE_BIRTH)
        return self

    def parsed_name_parts(self) -> dict[str, str | None]:
        """Fill missing name parts from ``full_name``."""
        parts = parse_full_name(self.full_name)
        return {
            field: getattr(self, field) or parts[field]
            for field in ("first_name", "father_name", "grandfather_name", "family_name")
        }

    def validated_national_id(self) -> str | None:
        """Validate the national ID against gender and birth date.

        Returns:
            The canonical 14-digit string, or ``None`` when absent.

        Raises:
            ValueError: with an Arabic message on any mismatch.
        """
        info = validate_national_id(
            self.national_id, birth_date=self.birth_date, gender=self.gender
        )
        return info.national_id if info else None


class PersonCreate(PersonBase):
    """POST /persons body."""

    #: Automatically inherit the father's family name when omitted.
    inherit_family_name: bool = True


class PersonUpdate(BaseModel):
    """PATCH /persons/{id} body - every field optional."""

    national_id: str | None = Field(default=None, max_length=14)
    full_name: str | None = Field(default=None, min_length=1, max_length=300)
    first_name: str | None = Field(default=None, max_length=100)
    father_name: str | None = Field(default=None, max_length=100)
    grandfather_name: str | None = Field(default=None, max_length=100)
    family_name: str | None = Field(default=None, max_length=100)
    gender: Gender | None = None
    birth_date: date | None = None
    death_date: date | None = None
    birth_place: str | None = Field(default=None, max_length=255)
    father_id: int | None = None
    mother_id: int | None = None
    notes: str | None = None

    @field_validator("full_name")
    @classmethod
    def _name_required(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError(Messages.FULL_NAME_REQUIRED)
        return value

    @field_validator("gender", mode="before")
    @classmethod
    def _gender_normalize(cls, value: Any) -> str | None:
        return _normalize_gender(value)


class PersonRef(BaseModel):
    """A lightweight person reference used inside tree/relationship payloads."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    gender: Gender | None = None
    birth_date: date | None = None
    death_date: date | None = None
    birth_place: str | None = None
    father_id: int | None = None
    mother_id: int | None = None


class PersonOut(PersonBase):
    """Full person representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    national_id: str | None = None
    national_id_masked: bool = Field(
        default=False, description="هل تم إخفاء رقم القومى حسب صلاحية المستخدم"
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: int | None = None
    updated_by: int | None = None
    merged_into_id: int | None = None
    father: PersonRef | None = None
    mother: PersonRef | None = None

    @classmethod
    def from_model(cls, person: Any, *, mask_national_id: bool = False) -> PersonOut:
        """Build a response object, masking the national ID when required."""
        data = {
            "id": person.id,
            "national_id": None,
            "national_id_masked": False,
            "full_name": person.full_name,
            "first_name": person.first_name,
            "father_name": person.father_name,
            "grandfather_name": person.grandfather_name,
            "family_name": person.family_name,
            "gender": person.gender,
            "birth_date": person.birth_date,
            "death_date": person.death_date,
            "birth_place": person.birth_place,
            "father_id": person.father_id,
            "mother_id": person.mother_id,
            "notes": person.notes,
            "created_at": person.created_at,
            "updated_at": person.updated_at,
            "created_by": person.created_by,
            "updated_by": person.updated_by,
            "merged_into_id": person.merged_into_id,
            "father": person.father,
            "mother": person.mother,
        }
        if mask_national_id and person.national_id:
            from app.utils.national_id import mask_national_id as _mask

            data["national_id"] = _mask(person.national_id)
            data["national_id_masked"] = True
        else:
            data["national_id"] = person.national_id
        return cls(**data)


class PersonListItem(PersonOut):
    """Trimmed person payload for list endpoints."""


class PersonSearchResult(BaseModel):
    """A person plus match metadata, used by the search endpoint."""

    person: PersonOut
    score: float = Field(..., description="درجة المطابقة من 0 إلى 1")
    matched_by: str = Field(..., description="نوع المطابقة: exact / fuzzy / national_id")


class PersonDeleteResult(BaseModel):
    """Result of a delete request."""

    id: int
    deleted: bool
    message: str
