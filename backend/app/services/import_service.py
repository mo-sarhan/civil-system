"""Import pipeline: upload -> preview -> map -> validate -> commit.

Design notes
------------
* Files are streamed row by row; nothing is loaded fully into memory, so a
  500k-row XLSX costs the same RAM as a 50-row one.
* Validation is a full pass that **never** writes to ``person``; it produces an
  Arabic error report the user reviews before committing.
* Committing runs in a background thread and upserts in chunks.  Matching is by
  ``national_id`` first, then by ``(normalised name, birth_date)`` - so
  re-importing the same file updates rows instead of duplicating them.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, PayloadTooLargeError, ValidationError
from app.core.pagination import as_date, utcnow
from app.db.session import SessionLocal
from app.models.import_job import ImportJob, ImportMappingTemplate, ImportStatus
from app.models.person import Person
from app.utils.arabic import normalize_name, parse_full_name
from app.utils.messages import Messages
from app.utils.national_id import validate_national_id

logger = logging.getLogger(__name__)

#: Maximum number of individual errors stored per job.
MAX_REPORTED_ERRORS = 2000

LinkingMode = str  # "by_national_id" | "by_name" | "none"

LINKING_MODES: dict[str, str] = {
    "by_national_id": "ربط الوالدين عبر رقم القومى",
    "by_name": "ربط الوالدين عبر الاسم (مع سنة الميلاد)",
    "none": "استيراد الأشخاص فقط",
}

#: Target fields the user can map. ``aliases`` drives the auto-detection.
FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "national_id": {
        "label": "رقم القومى",
        "aliases": [
            "national_id",
            "nationalid",
            "nid",
            "رقم القومى",
            "الرقم القومي",
            "رقم قومي",
            "قومي",
        ],
        "required": False,
    },
    "full_name": {
        "label": "الاسم الكامل",
        "aliases": ["full_name", "name", "الاسم", "الاسم بالكامل", "الاسم الرباعي", "الاسم كامل"],
        "required": True,
    },
    "first_name": {
        "label": "الاسم الأول",
        "aliases": ["first_name", "firstname", "الاسم الأول"],
        "required": False,
    },
    "father_name": {
        "label": "اسم الأب",
        "aliases": [
            "father_name",
            "fathername",
            "father_full_name",
            "اسم الأب",
            "اسم الاب",
            "اسم الوالد",
            "ابو",
        ],
        "required": False,
    },
    "grandfather_name": {
        "label": "اسم الجد",
        "aliases": ["grandfather_name", "grandfathername", "اسم الجد"],
        "required": False,
    },
    "family_name": {
        "label": "اسم العائلة",
        "aliases": [
            "family_name",
            "last_name",
            "familyname",
            "lastname",
            "اسم العائلة",
            "النسب",
            "اللقب",
        ],
        "required": False,
    },
    "gender": {
        "label": "النوع",
        "aliases": ["gender", "sex", "type", "النوع", "الجنس", "الذكر أو الأنثى"],
        "required": False,
    },
    "birth_date": {
        "label": "تاريخ الميلاد",
        "aliases": ["birth_date", "birthdate", "dob", "date_of_birth", "تاريخ الميلاد", "ميلاد"],
        "required": False,
    },
    "death_date": {
        "label": "تاريخ الوفاة",
        "aliases": ["death_date", "deathdate", "dod", "تاريخ الوفاة", "الوفاة"],
        "required": False,
    },
    "birth_place": {
        "label": "مكان الميلاد",
        "aliases": [
            "birth_place",
            "birthplace",
            "place_of_birth",
            "مكان الميلاد",
            "محافظة الميلاد",
        ],
        "required": False,
    },
    "notes": {
        "label": "ملاحظات",
        "aliases": ["notes", "note", "comment", "ملاحظات", "تعليقات"],
        "required": False,
    },
    "father_national_id": {
        "label": "رقم قومى الأب",
        "aliases": [
            "father_national_id",
            "father_nid",
            "father_id_number",
            "رقم قومى الأب",
            "رقم القومى للاب",
        ],
        "required": False,
    },
    "mother_national_id": {
        "label": "رقم قومى الأم",
        "aliases": ["mother_national_id", "mother_nid", "mother_id_number", "رقم قومى الأم"],
        "required": False,
    },
    "mother_name": {
        "label": "اسم الأم (للربط)",
        "aliases": ["mother_name", "mother_full_name", "اسم الام", "ام"],
        "required": False,
    },
    "father_birth_year": {
        "label": "سنة ميلاد الأب",
        "aliases": ["father_birth_year", "fby", "سنة ميلاد الاب"],
        "required": False,
    },
    "mother_birth_year": {
        "label": "سنة ميلاد الأم",
        "aliases": ["mother_birth_year", "mby", "سنة ميلاد الام"],
        "required": False,
    },
}

PERSON_FIELDS = [
    "national_id",
    "full_name",
    "first_name",
    "father_name",
    "grandfather_name",
    "family_name",
    "gender",
    "birth_date",
    "death_date",
    "birth_place",
    "notes",
]

TEMPLATE_COLUMNS = [
    "national_id",
    "full_name",
    "gender",
    "birth_date",
    "birth_place",
    "father_national_id",
    "mother_national_id",
    "notes",
]

SAMPLE_ROWS = [
    {
        "national_id": "24003151200113",
        "full_name": "محمد أحمد السيد",
        "gender": "M",
        "birth_date": "1940-03-15",
        "birth_place": "القاهرة",
        "father_national_id": "",
        "mother_national_id": "",
        "notes": "مثال",
    },
    {
        "national_id": "26502101200315",
        "full_name": "أحمد محمد أحمد",
        "gender": "M",
        "birth_date": "1965-02-10",
        "birth_place": "القاهرة",
        "father_national_id": "24003151200113",
        "mother_national_id": "24507201200224",
        "notes": "مثال",
    },
]


@dataclass
class RowError:
    """One validation problem, ready to be shown in the UI."""

    row: int
    field: str
    value: str | None
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "field": self.field,
            "value": self.value,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass
class RowRecord:
    """A parsed and normalised file row."""

    row_number: int
    values: dict[str, Any]
    national_id: str | None = None
    full_name: str = ""
    normalized_name: str = ""
    gender: str | None = None
    birth_date: date | None = None
    death_date: date | None = None
    father_id: int | None = None
    mother_id: int | None = None
    errors: list[RowError] = dataclass_field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(e.severity == "error" for e in self.errors)

    @property
    def key(self) -> tuple[str, str, str]:
        return (
            self.national_id or "",
            self.normalized_name,
            self.birth_date.isoformat() if self.birth_date else "",
        )


# --------------------------------------------------------------------------- #
# File readers
# --------------------------------------------------------------------------- #
def read_headers(file_path: Path) -> list[str]:
    """First non-empty row of the file, treated as the header."""
    for row in _iter_raw_rows(file_path):
        return [str(cell).strip() for cell in row]
    return []


def iter_rows(file_path: Path, limit: int | None = None) -> Iterator[list[Any]]:
    """Yield data rows (header excluded)."""
    first = True
    count = 0
    for row in _iter_raw_rows(file_path):
        if first:
            first = False
            continue
        if not any(str(cell).strip() for cell in row):
            continue
        count += 1
        if limit is not None and count > limit:
            return
        yield row


def _iter_raw_rows(file_path: Path) -> Iterator[Sequence[Any]]:
    if file_path.suffix.lower() in {".xlsx", ".xlsm"}:
        yield from _iter_xlsx(file_path)
    else:
        yield from _iter_csv(file_path)


def _iter_csv(file_path: Path) -> Iterator[list[str]]:
    # utf-8-sig strips the BOM Excel writes, which would otherwise corrupt the
    # first header cell.
    with file_path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect: Any = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        yield from csv.reader(handle, dialect)


def _iter_xlsx(file_path: Path) -> Iterator[list[Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(filename=file_path, read_only=True, data_only=True)
    try:
        sheet = workbook[workbook.sheetnames[0]]
        for row in sheet.iter_rows(values_only=True):
            yield list(row)
    finally:
        workbook.close()


def count_rows(file_path: Path) -> int:
    """Total data-row count without loading the file."""
    return sum(1 for _ in iter_rows(file_path))


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #
def guess_mapping(headers: Sequence[str]) -> dict[str, int]:
    """Best-effort automatic mapping of headers to system fields."""
    mapping: dict[str, int] = {}
    normalized_headers = [normalize_name(h) for h in headers]
    for field, meta in FIELD_DEFINITIONS.items():
        for index, header in enumerate(normalized_headers):
            if not header:
                continue
            if header in meta["aliases"]:
                mapping[field] = index
                break
        if field in mapping:
            continue
        for index, header in enumerate(normalized_headers):
            if not header:
                continue
            for alias in meta["aliases"]:
                alias_norm = normalize_name(alias)
                if alias_norm and (alias_norm in header or header in alias_norm):
                    mapping[field] = index
                    break
            if field in mapping:
                break
    return mapping


class ImportService:
    """Drives one import job through its lifecycle."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Job access
    # ------------------------------------------------------------------ #
    def get_job(self, job_id: int) -> ImportJob:
        job = self.db.get(ImportJob, job_id)
        if job is None:
            raise NotFoundError(Messages.IMPORT_JOB_NOT_FOUND)
        return job

    def cancel_job(self, job: ImportJob) -> ImportJob:
        """Mark a job cancelled.

        A running commit checks this status between chunks and stops, so rows it
        already committed stay committed; a job that is still pending or ready is
        cancelled outright.
        """
        if job.status in {ImportStatus.COMPLETED.value, ImportStatus.CANCELLED.value}:
            raise ValidationError(Messages.IMPORT_INVALID_STATUS)
        was_processing = job.status == ImportStatus.PROCESSING.value
        job.status = ImportStatus.CANCELLED.value
        job.message = (
            "تم إلغاء الاستيراد - تم حفظ الصفوف التي تمت معالجتها"
            if was_processing and (job.success_rows or job.created_rows or job.updated_rows)
            else "تم إلغاء الاستيراد"
        )
        job.committed_at = utcnow()
        job.updated_at = utcnow()
        self.db.commit()
        return job

    def _path(self, job: ImportJob) -> Path:
        if not job.stored_path:
            raise ValidationError(Messages.IMPORT_FILE_EMPTY)
        path = Path(job.stored_path)
        if not path.exists():
            raise NotFoundError("ملف الاستيراد غير موجود على الخادم")
        return path

    def _effective_mapping(self, job: ImportJob, path: Path) -> dict[str, int]:
        """The confirmed column mapping, falling back to auto-detection.

        ``POST /imports/jobs/{id}/mapping`` is how a user confirms or corrects
        the guess, but a wizard that stops at ``validate`` must not reject every
        row just because ``full_name`` is still unmapped, so the guessed mapping
        is used until a mapping has been stored.
        """
        mapping: dict[str, int] = dict(job.column_mapping or {})
        if "full_name" in mapping:
            return mapping
        return guess_mapping(read_headers(path))

    # ------------------------------------------------------------------ #
    # Steps
    # ------------------------------------------------------------------ #
    def preview(self, job: ImportJob, rows: int = 20) -> dict[str, Any]:
        """Header row, the first ``rows`` data rows and a guessed mapping."""
        path = self._path(job)
        headers = read_headers(path)
        preview_rows = [list(r) for r in iter_rows(path, limit=rows)]
        total = job.total_rows or count_rows(path)
        return {
            "job_id": job.id,
            "filename": job.filename,
            "headers": headers,
            "rows": preview_rows,
            "total_rows": total,
            "suggested_mapping": guess_mapping(headers),
            "fields": [
                {
                    "key": key,
                    "label": meta["label"],
                    "required": meta["required"],
                    "available": key in guess_mapping(headers),
                }
                for key, meta in FIELD_DEFINITIONS.items()
            ],
            "linking_modes": LINKING_MODES,
        }

    def set_mapping(
        self,
        job: ImportJob,
        mapping: dict[str, int],
        linking_mode: str,
        *,
        actor_id: int | None = None,
    ) -> ImportJob:
        """Persist the user's column mapping and linking mode."""
        if linking_mode not in LINKING_MODES:
            raise ValidationError(f"نمط ربط غير معروف: {linking_mode}")
        headers = read_headers(self._path(job))
        if not headers:
            raise ValidationError(Messages.IMPORT_FILE_EMPTY)

        cleaned: dict[str, int] = {}
        for field, index in mapping.items():
            if field not in FIELD_DEFINITIONS:
                raise ValidationError(f"حقل غير معروف في المطابقة: {field}")
            try:
                index = int(index)
            except (TypeError, ValueError):
                raise ValidationError(f"رقم عمود غير صحيح للحقل {field}") from None
            if not 0 <= index < len(headers):
                raise ValidationError(Messages.IMPORT_MAPPING_INVALID)
            cleaned[field] = index

        if "full_name" not in cleaned:
            raise ValidationError(f"{Messages.IMPORT_NO_MAPPING}: يجب.mapping حقل الاسم الكامل")
        if job.total_rows and job.total_rows > settings.import_max_rows:
            raise PayloadTooLargeError(
                f"عدد الصفوف ({job.total_rows}) يتجاوز الحد المسموح ({settings.import_max_rows})"
            )

        job.column_mapping = cleaned
        job.linking_mode = linking_mode
        job.status = ImportStatus.PENDING.value
        job.error_report = None
        job.warnings = None
        job.progress = 0
        self.db.commit()
        self.db.refresh(job)
        return job

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #
    def validate(self, job: ImportJob, *, max_errors: int = MAX_REPORTED_ERRORS) -> dict[str, Any]:
        """Full validation pass; no writes to ``person``."""
        job.status = ImportStatus.VALIDATING.value
        job.error_report = []
        job.warnings = []
        self.db.commit()

        path = self._path(job)
        mapping = self._effective_mapping(job, path)
        linking_mode = job.linking_mode or "none"

        errors: list[RowError] = []
        total_errors = 0
        total_warnings = 0
        valid_rows = 0
        invalid_rows = 0
        seen_national_ids: dict[str, int] = {}
        total = 0

        resolver = LinkResolver(self.db, linking_mode)

        for row_number, row in enumerate(iter_rows(path), start=2):  # row 1 = header
            total += 1
            record = self._build_record(row_number, row, mapping)
            record.errors.extend(self._validate_person_fields(record))
            record.errors.extend(self._validate_file_uniqueness(record, seen_national_ids))
            try:
                resolver.resolve(record)
            except Exception as exc:  # pragma: no cover - defensive
                record.errors.append(
                    RowError(row_number, "parents", None, f"تعذر التحقق من الوالدين: {exc}")
                )

            if record.has_errors:
                invalid_rows += 1
                total_errors += sum(1 for e in record.errors if e.severity == "error")
                total_warnings += sum(1 for e in record.errors if e.severity == "warning")
                for error in record.errors:
                    if len(errors) < max_errors:
                        errors.append(error)
            else:
                valid_rows += 1

            if total % 10_000 == 0:
                job.progress = int(100 * total / max(1, job.total_rows or total))
                job.processed_rows = total
                self.db.commit()

        job.total_rows = total
        job.processed_rows = total
        job.failed_rows = invalid_rows
        job.error_report = [e.as_dict() for e in errors]
        job.warnings = (
            [
                {
                    "total": total_warnings,
                    "truncated": total_errors + total_warnings > len(errors),
                    "message": "تم حفظ أول الأخطاء فقط في التقرير",
                }
            ]
            if total_warnings or total_errors > len(errors)
            else []
        )
        job.status = ImportStatus.READY.value
        job.progress = 0
        self.db.commit()
        self.db.refresh(job)

        return {
            "job_id": job.id,
            "status": job.status,
            "total_rows": total,
            "valid_rows": valid_rows,
            "invalid_rows": invalid_rows,
            "errors_count": total_errors,
            "warnings_count": total_warnings,
            "errors": [e.as_dict() for e in errors[:200]],
            "errors_truncated": total_errors + total_warnings > len(errors),
            "linking_mode": linking_mode,
            "can_commit": valid_rows > 0,
        }

    def _build_record(
        self, row_number: int, row: Sequence[Any], mapping: dict[str, int]
    ) -> RowRecord:
        values: dict[str, Any] = {}
        for field, index in mapping.items():
            cell = row[index] if 0 <= index < len(row) else None
            values[field] = cell.strip() if isinstance(cell, str) else cell
        full_name = str(values.get("full_name") or "").strip()
        return RowRecord(
            row_number=row_number,
            values=values,
            full_name=full_name,
            normalized_name=normalize_name(full_name),
        )

    @staticmethod
    def _validate_person_fields(record: RowRecord) -> list[RowError]:
        errors: list[RowError] = []
        values = record.values

        if not record.full_name:
            errors.append(RowError(record.row_number, "full_name", "", Messages.FULL_NAME_REQUIRED))
            return errors

        record.gender = _parse_gender(values.get("gender"))
        if values.get("gender") not in (None, "") and record.gender is None:
            errors.append(
                RowError(
                    record.row_number, "gender", str(values.get("gender")), Messages.GENDER_INVALID
                )
            )

        raw_birth = values.get("birth_date")
        if raw_birth not in (None, ""):
            record.birth_date = as_date(raw_birth)
            if record.birth_date is None:
                errors.append(
                    RowError(
                        record.row_number,
                        "birth_date",
                        str(raw_birth),
                        "تاريخ الميلاد غير مفهوم، الصيغة المقبولة: YYYY-MM-DD أو DD/MM/YYYY",
                    )
                )
            elif record.birth_date > date.today():
                errors.append(
                    RowError(
                        record.row_number, "birth_date", str(raw_birth), Messages.BIRTH_IN_FUTURE
                    )
                )

        raw_death = values.get("death_date")
        if raw_death not in (None, ""):
            record.death_date = as_date(raw_death)
            if record.death_date is None:
                errors.append(
                    RowError(
                        record.row_number,
                        "death_date",
                        str(raw_death),
                        "تاريخ الوفاة غير مفهوم، الصيغة المقبولة: YYYY-MM-DD أو DD/MM/YYYY",
                    )
                )

        if record.birth_date and record.death_date and record.death_date < record.birth_date:
            errors.append(
                RowError(
                    record.row_number, "death_date", str(raw_death), Messages.DEATH_BEFORE_BIRTH
                )
            )

        raw_national_id = values.get("national_id")
        if raw_national_id not in (None, ""):
            try:
                info = validate_national_id(
                    str(raw_national_id),
                    birth_date=record.birth_date,
                    gender=record.gender,
                )
                record.national_id = info.national_id if info else None
            except ValueError as exc:
                errors.append(
                    RowError(record.row_number, "national_id", str(raw_national_id), str(exc))
                )

        # Parent gender / age rules against the resolved parents are checked by
        # the LinkResolver; here we only sanity-check the *values*.
        for field in ("father_birth_year", "mother_birth_year"):
            raw = values.get(field)
            if raw not in (None, ""):
                try:
                    year = int(str(raw).strip()[:4])
                except ValueError:
                    errors.append(
                        RowError(record.row_number, field, str(raw), "سنة الميلاد يجب أن تكون رقماً")
                    )
                    continue
                if record.birth_date and abs(record.birth_date.year - year) > 120:
                    errors.append(
                        RowError(
                            record.row_number,
                            field,
                            str(raw),
                            "سنة ميلاد الوالد بعيدة جداً عن سنة ميلاد الابن",
                        )
                    )
        return errors

    @staticmethod
    def _validate_file_uniqueness(record: RowRecord, seen: dict[str, int]) -> list[RowError]:
        if not record.national_id:
            return []
        if record.national_id in seen:
            return [
                RowError(
                    record.row_number,
                    "national_id",
                    record.national_id,
                    f"رقم القومى مكرر داخل الملف (موجود أيضاً في السطر {seen[record.national_id]})",
                )
            ]
        seen[record.national_id] = record.row_number
        return []

    # ------------------------------------------------------------------ #
    # Commit
    # ------------------------------------------------------------------ #
    def commit_async(
        self,
        job: ImportJob,
        *,
        actor_id: int | None,
        skip_invalid: bool = True,
    ) -> ImportJob:
        """Start the background commit and return immediately."""
        if job.status != ImportStatus.READY.value:
            raise ValidationError(Messages.IMPORT_INVALID_STATUS)
        job.status = ImportStatus.PROCESSING.value
        job.progress = 0
        job.committed_by = actor_id
        job.message = "جارٍ التنفيذ..."
        self.db.commit()

        thread = threading.Thread(
            target=self._commit_worker,
            args=(job.id, actor_id, skip_invalid),
            name=f"import-{job.id}",
            daemon=True,
        )
        thread.start()
        return job

    def commit_sync(
        self,
        job: ImportJob,
        *,
        actor_id: int | None,
        skip_invalid: bool = True,
    ) -> dict[str, Any]:
        """Synchronous variant used by tests and the CLI."""
        if job.status not in {ImportStatus.READY.value, ImportStatus.PENDING.value}:
            raise ValidationError(Messages.IMPORT_INVALID_STATUS)
        job.status = ImportStatus.PROCESSING.value
        job.progress = 0
        self.db.commit()
        return self._commit_worker(job.id, actor_id, skip_invalid)

    def _commit_worker(
        self, job_id: int, actor_id: int | None, skip_invalid: bool
    ) -> dict[str, Any]:
        """Run the streaming upsert in its own session."""
        session = SessionLocal()
        try:
            job = session.get(ImportJob, job_id)
            if job is None:  # pragma: no cover - job deleted mid-flight
                return {"status": "failed"}
            path = Path(job.stored_path or "")
            linking_mode = job.linking_mode or "none"
            chunk_size = settings.import_chunk_size
            total_rows = job.total_rows or count_rows(path)

            stats = {"created": 0, "updated": 0, "failed": 0}
            processed = 0
            failures: list[dict[str, Any]] = []
            chunk: list[RowRecord] = []

            service = self.__class__(session)
            mapping = service._effective_mapping(job, path)
            resolver = LinkResolver(session, linking_mode)

            def flush(records: list[RowRecord]) -> None:
                nonlocal stats
                if not records:
                    return
                try:
                    result = service._upsert_chunk(records, resolver, actor_id=actor_id)
                except Exception as exc:
                    session.rollback()
                    logger.exception("import chunk failed for job %s", job_id)
                    for record in records:
                        stats["failed"] += 1
                        if len(failures) < 200:
                            failures.append(
                                RowError(
                                    record.row_number, "*", None, f"فشل الحفظ: {exc}"
                                ).as_dict()
                            )
                    return
                stats["created"] += result["created"]
                stats["updated"] += result["updated"]
                stats["failed"] += result["failed"]
                for failure in result["failures"][:200]:
                    if len(failures) < 200:
                        failures.append(failure)

            for row_number, row in enumerate(iter_rows(path), start=2):
                processed += 1
                record = service._build_record(row_number, row, mapping)
                record.errors.extend(service._validate_person_fields(record))
                try:
                    resolver.resolve(record)
                except Exception:  # pragma: no cover - defensive
                    logger.exception("parent resolution failed at row %s", row_number)

                if record.has_errors:
                    if skip_invalid:
                        stats["failed"] += 1
                        if len(failures) < 200:
                            for error in record.errors:
                                if error.severity == "error":
                                    failures.append(error.as_dict())
                                    break
                    else:
                        stats["failed"] += 1
                        failures.append(
                            RowError(
                                row_number, "*", None, Messages.IMPORT_INVALID_STATUS
                            ).as_dict()
                        )
                else:
                    chunk.append(record)
                    if len(chunk) >= chunk_size:
                        flush(chunk)
                        chunk = []
                        # Pull any cancel written by another session. This also
                        # discards local uncommitted job changes, so all writes
                        # below must come after it.
                        session.refresh(job)
                        if job.status == ImportStatus.CANCELLED.value:
                            self._finalise_cancelled(session, job, stats, processed, total_rows)
                            return {"status": "cancelled"}
                        job.processed_rows = processed
                        job.progress = int(100 * processed / max(1, total_rows))
                        job.created_rows = stats["created"]
                        job.updated_rows = stats["updated"]
                        job.failed_rows = stats["failed"]
                        session.commit()

            flush(chunk)

            session.refresh(job)
            if job.status == ImportStatus.CANCELLED.value:
                self._finalise_cancelled(session, job, stats, processed, total_rows)
                return {"status": "cancelled"}
            job.processed_rows = processed
            job.total_rows = total_rows
            job.created_rows = stats["created"]
            job.updated_rows = stats["updated"]
            job.success_rows = stats["created"] + stats["updated"]
            job.failed_rows = stats["failed"]
            job.progress = 100
            job.status = (
                ImportStatus.COMPLETED.value if job.success_rows else ImportStatus.FAILED.value
            )
            job.committed_at = utcnow()
            job.message = (
                f"تم استيراد {job.success_rows} سجل "
                f"({stats['created']} جديد، {stats['updated']} تحديث)"
                + (f" - فشل {stats['failed']}" if stats["failed"] else "")
            )
            if failures:
                existing = job.error_report or []
                job.error_report = (existing + failures)[:MAX_REPORTED_ERRORS]
            job.updated_at = utcnow()
            session.commit()
            return {"status": job.status, **stats}
        except Exception as exc:  # pragma: no cover - worker-level failure
            logger.exception("import worker failed for job %s", job_id)
            try:
                session.rollback()
                job = session.get(ImportJob, job_id)
                if job:
                    job.status = ImportStatus.FAILED.value
                    job.message = f"فشل الاستيراد: {exc}"[:500]
                    session.commit()
            except Exception:
                logger.exception("could not record import failure")
            return {"status": "failed", "error": str(exc)}
        finally:
            session.close()

    @staticmethod
    def _finalise_cancelled(
        session: Session,
        job: ImportJob,
        stats: dict[str, int],
        processed: int,
        total_rows: int,
    ) -> None:
        """Close out a job that a user cancelled mid-flight."""
        job.processed_rows = processed
        job.total_rows = total_rows
        job.created_rows = stats["created"]
        job.updated_rows = stats["updated"]
        job.success_rows = stats["created"] + stats["updated"]
        job.failed_rows = stats["failed"]
        job.progress = int(100 * processed / max(1, total_rows))
        job.status = ImportStatus.CANCELLED.value
        job.message = (
            f"تم إلغاء الاستيراد - تم حفظ {job.success_rows} سجل قبل الإلغاء"
            if job.success_rows
            else "تم إلغاء الاستيراد"
        )
        job.updated_at = utcnow()
        session.commit()

    def _upsert_chunk(
        self,
        records: list[RowRecord],
        resolver: LinkResolver,
        *,
        actor_id: int | None,
    ) -> dict[str, Any]:
        """Upsert a chunk of validated rows inside a single transaction.

        Each row is written inside a SAVEPOINT so one bad row never discards the
        rest of the chunk.  Matching is by national ID first, then by
        ``(normalised name, birth_date)``, which makes re-importing idempotent.
        """
        result = {"created": 0, "updated": 0, "failed": 0, "failures": []}

        national_ids = [r.national_id for r in records if r.national_id]
        existing_by_nid: dict[str, Person] = {}
        if national_ids:
            for person in self.db.query(Person).filter(Person.national_id.in_(national_ids)).all():
                if person.national_id:
                    existing_by_nid[person.national_id] = person

        existing_by_name: dict[tuple[str, date], Person] = {}
        unnamed = [r for r in records if not r.national_id and r.birth_date]
        if unnamed:
            names = {r.normalized_name for r in unnamed}
            dates = {r.birth_date for r in unnamed if r.birth_date}
            for person in (
                self.db.query(Person)
                .filter(Person.full_name_normalized.in_(names), Person.birth_date.in_(dates))
                .all()
            ):
                existing_by_name.setdefault(
                    (person.full_name_normalized, person.birth_date), person
                )

        for record in records:
            person: Person | None = None
            if record.national_id:
                person = existing_by_nid.get(record.national_id)
            if person is None and record.birth_date:
                person = existing_by_name.get((record.normalized_name, record.birth_date))

            try:
                with self.db.begin_nested():
                    if person is None:
                        person = Person(
                            full_name=record.full_name,
                            full_name_normalized=record.normalized_name,
                            created_by=actor_id,
                            updated_by=actor_id,
                        )
                        self.db.add(person)
                        result["created"] += 1
                    else:
                        person.updated_by = actor_id
                        result["updated"] += 1

                    self._apply_values(person, record)
                    if record.father_id:
                        person.father_id = record.father_id
                    if record.mother_id:
                        person.mother_id = record.mother_id
                    self.db.flush()
            except Exception as exc:
                result["failed"] += 1
                if len(result["failures"]) < 200:
                    result["failures"].append(
                        RowError(
                            record.row_number, "*", record.full_name, _db_error_message(exc)
                        ).as_dict()
                    )

            if person is not None:
                if record.national_id:
                    existing_by_nid[record.national_id] = person
                if record.birth_date:
                    existing_by_name.setdefault((record.normalized_name, record.birth_date), person)

        return result

    @staticmethod
    def _apply_values(person: Person, record: RowRecord) -> None:
        """Copy parsed row values onto a person row."""
        parts = parse_full_name(record.full_name)
        values = record.values
        person.full_name = record.full_name
        person.full_name_normalized = record.normalized_name
        if record.national_id:
            person.national_id = record.national_id
        if record.gender:
            person.gender = record.gender
        if record.birth_date:
            person.birth_date = record.birth_date
        if record.death_date:
            person.death_date = record.death_date
        for field in ("birth_place", "notes"):
            explicit = _as_text(values.get(field))
            if explicit:
                setattr(person, field, explicit)
        for field in ("first_name", "father_name", "grandfather_name", "family_name"):
            explicit = _as_text(values.get(field))
            setattr(person, field, explicit or getattr(person, field) or parts[field])

    # ------------------------------------------------------------------ #
    # Templates
    # ------------------------------------------------------------------ #
    def list_mapping_templates(self, user_id: int | None = None) -> list[ImportMappingTemplate]:
        stmt = select(ImportMappingTemplate).order_by(ImportMappingTemplate.name)
        if user_id:
            rows = self.db.execute(stmt).scalars().all()
            return [t for t in rows if t.is_shared or t.created_by == user_id]
        return list(self.db.execute(stmt).scalars().all())

    def create_mapping_template(
        self,
        *,
        name: str,
        mapping: dict[str, int],
        linking_mode: str,
        description: str | None = None,
        is_shared: bool = True,
        user_id: int | None = None,
    ) -> ImportMappingTemplate:
        template = ImportMappingTemplate(
            name=name,
            description=description,
            mapping=mapping,
            linking_mode=linking_mode,
            is_shared=is_shared,
            created_by=user_id,
        )
        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_mapping_template(self, template_id: int) -> None:
        template = self.db.get(ImportMappingTemplate, template_id)
        if template is None:
            raise NotFoundError("قالب المطابقة غير موجود")
        self.db.delete(template)
        self.db.commit()

    def list_jobs(self, limit: int = 50) -> list[ImportJob]:
        return list(
            self.db.execute(
                select(ImportJob).order_by(ImportJob.created_at.desc()).limit(limit)
            ).scalars()
        )


def _db_error_message(exc: Exception) -> str:
    """Translate a database constraint violation into an Arabic message."""
    text = str(exc)
    mapping = (
        ("person_cycle_detected", Messages.PARENT_CYCLE),
        ("uq_person_national_id", Messages.NATIONAL_ID_DUPLICATE),
        ("ck_person_national_id_14_digits", Messages.NATIONAL_ID_LENGTH),
        ("ck_person_gender", Messages.GENDER_INVALID),
        ("ck_person_death_after_birth", Messages.DEATH_BEFORE_BIRTH),
        ("ck_person_not_own", Messages.PARENT_SELF),
        ("ck_person_parents_distinct", "لا يمكن أن يكون الأب والوالدة نفس الشخص"),
    )
    for needle, message in mapping:
        if needle in text:
            return message
    return f"تعذر الحفظ: {text[:200]}"


def _as_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_gender(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"m", "male", "ذكر", "ذ", "1", "true"}:
        return "M"
    if text in {"f", "female", "انثى", "أنثى", "ا", "بنت", "0", "false"}:
        return "F"
    return None


class LinkResolver:
    """Resolves ``father_id``/``mother_id`` for imported rows.

    Modes:

    * ``by_national_id`` - look the parents up by their national ID.
    * ``by_name`` - match on the normalised full name plus an optional birth
      year; an ambiguous match is reported so the user can resolve it.
    * ``none`` - no parent links are created.
    """

    def __init__(self, db: Session, mode: str) -> None:
        self.db = db
        self.mode = mode
        self._by_national_id: dict[str, int] = {}
        self._by_name: dict[str, list[Person]] = {}
        self._year_hints: dict[int, int | None] = {}
        self._missing: dict[str, int | None] = {}

    def resolve(self, record: RowRecord) -> None:
        if self.mode == "none":
            return
        father_key = record.values.get("father_national_id") or record.values.get("father_name")
        mother_key = record.values.get("mother_national_id") or record.values.get("mother_name")
        if self.mode == "by_national_id":
            record.father_id = self._lookup_national_id(record, "father_national_id", father_key)
            record.mother_id = self._lookup_national_id(record, "mother_national_id", mother_key)
        else:
            record.father_id = self._lookup_name(record, "father", father_key)
            record.mother_id = self._lookup_name(record, "mother", mother_key)
        self._check_parent_rules(record)

    # -- by national id ---------------------------------------------------
    def _lookup_national_id(self, record: RowRecord, field: str, raw: Any) -> int | None:
        value = _as_text(raw)
        if not value:
            return None
        value = str(value).strip()
        if value.isdigit() and len(value) != 14:
            record.errors.append(
                RowError(record.row_number, field, value, Messages.NATIONAL_ID_LENGTH)
            )
            return None
        person_id = self._national_id_cache_get(value)
        if person_id is None:
            person = self.db.execute(
                select(Person).where(Person.national_id == value)
            ).scalar_one_or_none()
            person_id = person.id if person else None
            self._national_id_cache_put(value, person_id)
        if person_id is None:
            record.errors.append(
                RowError(
                    record.row_number,
                    field,
                    value,
                    f"{Messages.PARENT_NOT_FOUND} (رقم القومى: {value})",
                )
            )
        return person_id

    def _national_id_cache_get(self, value: str) -> int | None:
        return self._by_national_id.get(value, -1) if value in self._by_national_id else None

    def _national_id_cache_put(self, value: str, person_id: int | None) -> None:
        self._by_national_id[value] = person_id if person_id is not None else -1

    # -- by name ----------------------------------------------------------
    def _lookup_name(self, record: RowRecord, side: str, raw: Any) -> int | None:
        name = _as_text(raw)
        if not name:
            return None
        year = record.values.get(f"{side}_birth_year")
        try:
            year_int = int(str(year).strip()[:4]) if year not in (None, "") else None
        except (TypeError, ValueError):
            year_int = None

        normalized = normalize_name(name)
        if not normalized:
            return None
        candidates = self._by_name.get(normalized)
        if candidates is None:
            candidates = list(
                self.db.execute(
                    select(Person)
                    .where(
                        Person.full_name_normalized == normalized,
                        Person.merged_into_id.is_(None),
                    )
                    .limit(50)
                ).scalars()
            )
            self._by_name[normalized] = candidates

        if year_int is not None:
            candidates = [c for c in candidates if c.birth_date and c.birth_date.year == year_int]

        if not candidates:
            record.errors.append(
                RowError(
                    record.row_number,
                    f"{side}_name",
                    name,
                    f"{Messages.IMPORT_LINK_NOT_FOUND} ({'الأب' if side == 'father' else 'الأم'})",
                )
            )
            return None
        if len(candidates) > 1:
            listed = "، ".join(
                f"#{c.id} {c.full_name} ({c.birth_date.year if c.birth_date else 'بلا تاريخ'})"
                for c in candidates[:5]
            )
            record.errors.append(
                RowError(
                    record.row_number,
                    f"{side}_name",
                    name,
                    f"{Messages.IMPORT_LINK_AMBIGUOUS}: {listed}",
                )
            )
            return None
        return candidates[0].id

    # -- shared rules -----------------------------------------------------
    def _check_parent_rules(self, record: RowRecord) -> None:
        parents = {"father": record.father_id, "mother": record.mother_id}
        for side, parent_id in parents.items():
            if not parent_id:
                continue
            parent = self.db.get(Person, parent_id)
            if parent is None:
                continue
            expected = "M" if side == "father" else "F"
            if parent.gender and parent.gender != expected:
                record.errors.append(
                    RowError(
                        record.row_number,
                        f"{side}_name" if self.mode == "by_name" else f"{side}_national_id",
                        parent.full_name,
                        (
                            Messages.FATHER_MUST_BE_MALE
                            if side == "father"
                            else Messages.MOTHER_MUST_BE_FEMALE
                        ),
                    )
                )
            if parent.birth_date and record.birth_date:
                age = (record.birth_date - parent.birth_date).days / 365.2425
                if age < 0:
                    record.errors.append(
                        RowError(
                            record.row_number,
                            f"{side}_birth_year",
                            parent.full_name,
                            Messages.PARENT_DIED_BEFORE_CHILD,
                        )
                    )
                elif age < settings.min_parent_age_years:
                    record.errors.append(
                        RowError(
                            record.row_number,
                            f"{side}_birth_year",
                            parent.full_name,
                            Messages.PARENT_TOO_YOUNG.format(
                                actual=round(age, 1), required=settings.min_parent_age_years
                            ),
                        )
                    )


# --------------------------------------------------------------------------- #
# File helpers
# --------------------------------------------------------------------------- #
ALLOWED_SUFFIXES = {".csv", ".xlsx", ".xlsm"}


def validate_upload(filename: str, size_bytes: int) -> tuple[str, Path]:
    """Check the uploaded file and store it; returns ``(file_type, path)``.

    The client-supplied name is never used as a path: it is reduced to a safe
    ASCII-ish stem and prefixed with a random token, so ``../`` traversal and
    collisions between two uploads of ``people.csv`` are both impossible.
    """
    raw = Path(filename or "").name
    suffix = Path(raw).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ValidationError(Messages.IMPORT_UNSUPPORTED_TYPE)

    stem = normalize_name(Path(raw).stem)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-_")
    if len(stem) > 40:
        stem = stem[:40].strip("-_")
    safe_name = f"{uuid4().hex[:12]}-{stem or 'upload'}{suffix}"

    storage = Path(settings.import_storage_dir).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    target = (storage / safe_name).resolve()
    if target.parent != storage:  # pragma: no cover - defensive
        raise ValidationError(Messages.IMPORT_UNSUPPORTED_TYPE)
    return suffix.lstrip("."), target


def build_csv_template() -> str:
    """CSV template returned by ``GET /imports/template/csv``."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=TEMPLATE_COLUMNS)
    writer.writeheader()
    for row in SAMPLE_ROWS:
        writer.writerow(row)
    return buffer.getvalue()


def create_job(
    db: Session,
    *,
    filename: str,
    stored_path: str,
    file_type: str,
    total_rows: int,
    user_id: int | None,
) -> ImportJob:
    job = ImportJob(
        filename=filename,
        stored_path=str(stored_path),
        file_type=file_type,
        total_rows=total_rows,
        status=ImportStatus.PENDING.value,
        created_by=user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
