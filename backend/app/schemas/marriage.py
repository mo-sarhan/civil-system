"""Pydantic schemas for marriages."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.messages import Messages

MarriageStatusValue = Literal["married", "divorced", "widowed", "separated"]


class MarriageBase(BaseModel):
    """Fields accepted on create and update."""

    husband_id: int = Field(..., gt=0)
    wife_id: int = Field(..., gt=0)
    start_date: date | None = None
    end_date: date | None = None
    status: MarriageStatusValue = "married"
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> MarriageBase:
        if self.husband_id == self.wife_id:
            raise ValueError(Messages.MARRIAGE_SAME_PERSON)
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError(Messages.MARRIAGE_END_BEFORE_START)
        return self


class MarriageCreate(MarriageBase):
    """POST /marriages body."""


class MarriageUpdate(BaseModel):
    """PATCH /marriages/{id} body."""

    start_date: date | None = None
    end_date: date | None = None
    status: MarriageStatusValue | None = None
    notes: str | None = None


class MarriageOut(BaseModel):
    """Marriage representation with spouse details."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    husband_id: int
    wife_id: int
    start_date: date | None = None
    end_date: date | None = None
    status: str
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    husband_name: str | None = None
    wife_name: str | None = None


class MarriageDeleteResult(BaseModel):
    """Result of a marriage delete."""

    id: int
    deleted: bool
    message: str
