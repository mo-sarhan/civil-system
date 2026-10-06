"""Schema: users, person, marriage, audit_log, import_job

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Extensions ----------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")

    # --- users ---------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=80), nullable=False),
        sa.Column("full_name", sa.String(length=150), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint("role IN ('admin','editor','viewer')", name="ck_users_role"),
    )

    # --- person ---------------------------------------------------------
    op.create_table(
        "person",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("national_id", sa.String(length=14), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("full_name_normalized", sa.Text(), nullable=False, server_default=""),
        sa.Column("first_name", sa.String(length=100), nullable=True),
        sa.Column("father_name", sa.String(length=100), nullable=True),
        sa.Column("grandfather_name", sa.String(length=100), nullable=True),
        sa.Column("family_name", sa.String(length=100), nullable=True),
        sa.Column("gender", sa.String(length=1), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("death_date", sa.Date(), nullable=True),
        sa.Column("birth_place", sa.String(length=255), nullable=True),
        sa.Column("father_id", sa.Integer(), nullable=True),
        sa.Column("mother_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("merged_into_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("national_id", name="uq_person_national_id"),
        sa.ForeignKeyConstraint(["father_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["mother_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["merged_into_id"], ["person.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "national_id IS NULL OR national_id ~ '^[0-9]{14}$'",
            name="ck_person_national_id_14_digits",
        ),
        sa.CheckConstraint("gender IS NULL OR gender IN ('M','F')", name="ck_person_gender"),
        sa.CheckConstraint(
            "death_date IS NULL OR birth_date IS NULL OR death_date >= birth_date",
            name="ck_person_death_after_birth",
        ),
        sa.CheckConstraint("father_id IS NULL OR father_id <> id", name="ck_person_not_own_father"),
        sa.CheckConstraint("mother_id IS NULL OR mother_id <> id", name="ck_person_not_own_mother"),
        sa.CheckConstraint(
            "father_id IS NULL OR mother_id IS NULL OR father_id <> mother_id",
            name="ck_person_parents_distinct",
        ),
    )
    op.create_index("ix_person_father_id", "person", ["father_id"])
    op.create_index("ix_person_mother_id", "person", ["mother_id"])
    op.create_index("ix_person_merged_into_id", "person", ["merged_into_id"])
    op.create_index("ix_person_birth_date", "person", ["birth_date"])
    op.create_index("ix_person_birth_year", "person", [sa.text("date_part('year', birth_date)")])
    op.create_index("ix_person_family_name", "person", ["family_name"])
    op.create_index(
        "ix_person_full_name_trgm",
        "person",
        ["full_name_normalized"],
        postgresql_using="gin",
        postgresql_ops={"full_name_normalized": "gin_trgm_ops"},
    )

    # --- marriage -------------------------------------------------------
    op.create_table(
        "marriage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("husband_id", sa.Integer(), nullable=False),
        sa.Column("wife_id", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="married"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["husband_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["wife_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("husband_id <> wife_id", name="ck_marriage_distinct_partners"),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="ck_marriage_end_after_start",
        ),
        sa.CheckConstraint(
            "status IN ('married','divorced','widowed','separated')",
            name="ck_marriage_status",
        ),
    )
    op.create_index("ix_marriage_husband", "marriage", ["husband_id"])
    op.create_index("ix_marriage_wife", "marriage", ["wife_id"])
    op.create_index(
        "ix_marriage_partner_pair",
        "marriage",
        [sa.text("least(husband_id, wife_id)"), sa.text("greatest(husband_id, wife_id)")],
        unique=True,
    )

    # --- audit_log -------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("username", sa.String(length=80), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("entity", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])
    op.create_index("ix_audit_log_entity", "audit_log", ["entity"])
    op.create_index("ix_audit_log_created_at", "audit_log", ["created_at"])
    op.create_index("ix_audit_entity_created", "audit_log", ["entity", "created_at"])
    op.create_index("ix_audit_user_created", "audit_log", ["user_id", "created_at"])

    # --- import_job ------------------------------------------------------
    op.create_table(
        "import_job",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("stored_path", sa.String(length=500), nullable=True),
        sa.Column("file_type", sa.String(length=10), nullable=False, server_default="csv"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("total_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("linking_mode", sa.String(length=30), nullable=True),
        sa.Column("column_mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_report", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("committed_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["committed_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "status IN ('pending','validating','ready','processing','completed','failed','cancelled')",
            name="ck_import_job_status",
        ),
    )
    op.create_index("ix_import_job_status", "import_job", ["status"])
    op.create_index("ix_import_job_created_by", "import_job", ["created_by"])
    op.create_index("ix_import_job_created", "import_job", ["created_at"])

    op.create_table(
        "import_mapping_template",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("mapping", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("linking_mode", sa.String(length=30), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
    )

    # --- Triggers ---------------------------------------------------------
    # Mirrors app/utils/arabic.normalize_name so the stored full_name_normalized
    # always matches what the Python layer produces. Codepoints are written as
    # escapes: a literal "0610-064B" range would strip every Arabic letter.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION normalize_arabic_name(text) RETURNS text AS $$
            SELECT btrim(
                regexp_replace(
                    regexp_replace(
                        translate(
                            translate(
                                translate(
                                    translate(
                                        $1,
                                        '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹',
                                        '01234567890123456789'
                                    ),
                                    'أإآٱٲٳ', 'اااااا'
                                ),
                                'ة', 'ه'
                            ),
                            'ىئ', 'يي'
                        ),
                        '[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]', '', 'g'
                    ),
                    '[^A-Za-z0-9_\u0600-\u06ff]+', ' ', 'g'
                )
            )
        $$ LANGUAGE sql IMMUTABLE;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION person_set_normalized_name() RETURNS trigger AS $$
        BEGIN
            NEW.full_name_normalized := public.normalize_arabic_name(NEW.full_name);
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_person_normalize_name BEFORE INSERT OR UPDATE OF full_name "
        "ON person FOR EACH ROW EXECUTE FUNCTION person_set_normalized_name();"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION touch_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        """
    )
    for table in ("person", "users", "marriage", "import_job"):
        op.execute(
            f"CREATE TRIGGER trg_{table}_touch BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION touch_updated_at();"
        )

    # --- Cycle guard at the database level ---------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION person_no_cycle() RETURNS trigger AS $$
        DECLARE
            cyc integer;
        BEGIN
            IF NEW.father_id IS NOT NULL OR NEW.mother_id IS NOT NULL THEN
                -- Walk up from the new row through its parents; if we reach
                -- NEW.id at depth > 0 the new links close a loop. The depth
                -- cap keeps the recursion finite on corrupt data.
                WITH RECURSIVE anc(id, father_id, mother_id, depth) AS (
                    SELECT p.id, p.father_id, p.mother_id, 0
                    FROM person p WHERE p.id = NEW.id
                    UNION ALL
                    SELECT p.id, p.father_id, p.mother_id, a.depth + 1
                    FROM person p
                    JOIN anc a ON p.id IN (a.father_id, a.mother_id)
                    WHERE a.depth < 1000
                )
                SELECT 1 INTO cyc FROM anc WHERE depth > 0 AND id = NEW.id LIMIT 1;
                IF cyc IS NOT NULL THEN
                    RAISE EXCEPTION 'person_cycle_detected'
                        USING ERRCODE = 'check_violation';
                END IF;
            END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE CONSTRAINT TRIGGER trg_person_no_cycle AFTER INSERT OR UPDATE OF father_id, mother_id "
        "ON person DEFERRABLE INITIALLY DEFERRED "
        "FOR EACH ROW EXECUTE FUNCTION person_no_cycle();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_person_no_cycle ON person")
    op.execute("DROP FUNCTION IF EXISTS person_no_cycle()")
    for table in ("person", "users", "marriage", "import_job"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_touch ON {table}")
    op.execute("DROP FUNCTION IF EXISTS touch_updated_at()")
    op.execute("DROP TRIGGER IF EXISTS trg_person_normalize_name ON person")
    op.execute("DROP FUNCTION IF EXISTS person_set_normalized_name()")
    op.execute("DROP FUNCTION IF EXISTS normalize_arabic_name(text)")
    op.drop_table("import_mapping_template")
    op.drop_index("ix_import_job_created", table_name="import_job")
    op.drop_index("ix_import_job_created_by", table_name="import_job")
    op.drop_index("ix_import_job_status", table_name="import_job")
    op.drop_table("import_job")
    op.drop_index("ix_audit_user_created", table_name="audit_log")
    op.drop_index("ix_audit_entity_created", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_action", table_name="audit_log")
    op.drop_index("ix_audit_log_user_id", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_marriage_partner_pair", table_name="marriage")
    op.drop_index("ix_marriage_wife", table_name="marriage")
    op.drop_index("ix_marriage_husband", table_name="marriage")
    op.drop_table("marriage")
    op.drop_index("ix_person_full_name_trgm", table_name="person")
    op.drop_index("ix_person_family_name", table_name="person")
    op.drop_index("ix_person_birth_year", table_name="person")
    op.drop_index("ix_person_birth_date", table_name="person")
    op.drop_index("ix_person_merged_into_id", table_name="person")
    op.drop_index("ix_person_mother_id", table_name="person")
    op.drop_index("ix_person_father_id", table_name="person")
    op.drop_table("person")
    op.drop_table("users")
