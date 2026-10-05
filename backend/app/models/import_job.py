"""Background import jobs and saved column-mapping templates."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ImportStatus(str, Enum):
    """Lifecycle of an import job."""

    PENDING = "pending"
    VALIDATING = "validating"
    READY = "ready"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportJob(Base):
    """Tracks one uploaded file through validate -> commit."""

    __tablename__ = "import_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column("filename", String(255), nullable=False)
    stored_path: Mapped[str | None] = mapped_column("stored_path", String(500))
    file_type: Mapped[str] = mapped_column("file_type", String(10), default="csv")
    status: Mapped[str] = mapped_column(
        "status", String(20), nullable=False, default=ImportStatus.PENDING.value, index=True
    )
    total_rows: Mapped[int] = mapped_column("total_rows", Integer, default=0, nullable=False)
    processed_rows: Mapped[int] = mapped_column(
        "processed_rows", Integer, default=0, nullable=False
    )
    success_rows: Mapped[int] = mapped_column("success_rows", Integer, default=0, nullable=False)
    failed_rows: Mapped[int] = mapped_column("failed_rows", Integer, default=0, nullable=False)
    updated_rows: Mapped[int] = mapped_column("updated_rows", Integer, default=0, nullable=False)
    created_rows: Mapped[int] = mapped_column("created_rows", Integer, default=0, nullable=False)
    linking_mode: Mapped[str | None] = mapped_column("linking_mode", String(30))
    column_mapping: Mapped[dict | None] = mapped_column("column_mapping", JSONB)
    error_report: Mapped[list | None] = mapped_column("error_report", JSONB)
    warnings: Mapped[list | None] = mapped_column("warnings", JSONB)
    progress: Mapped[int] = mapped_column("progress", Integer, default=0, nullable=False)
    message: Mapped[str | None] = mapped_column("message", Text)
    created_by: Mapped[int | None] = mapped_column(
        "created_by", ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    committed_by: Mapped[int | None] = mapped_column(
        "committed_by", ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        "updated_at",
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    committed_at: Mapped[datetime | None] = mapped_column("committed_at", DateTime(timezone=True))

    __table_args__ = (Index("ix_import_job_created", "created_at"),)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ImportJob {self.id} {self.filename} {self.status}>"


class ImportMappingTemplate(Base):
    """A reusable column mapping saved by an editor."""

    __tablename__ = "import_mapping_template"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column("name", String(120), nullable=False)
    description: Mapped[str | None] = mapped_column("description", String(255))
    mapping: Mapped[dict] = mapped_column("mapping", JSONB, nullable=False)
    linking_mode: Mapped[str | None] = mapped_column("linking_mode", String(30))
    is_shared: Mapped[bool] = mapped_column("is_shared", Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        "created_by", ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        "created_at", DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ImportMappingTemplate {self.name}>"
