"""add duplicate-detection expression indexes

Revision ID: 0002_duplicate_indexes
Revises: 0001_initial
Create Date: 2026-10-06

The fuzzy duplicate scan joins ``person`` against itself, restricted to rows that
share a birth year and one of the first two name tokens. Both predicates are
expressions over columns, so without these indexes the planner falls back to a
sequential nested loop whose cost grows quadratically with the table.

The indexes are partial (``merged_into_id IS NULL``) because merged redirect
rows are never candidates, which keeps them small.

Measured on 200k synthetic persons spread over 100 birth years, ``LIMIT 200``::

    before: 1062 ms  Gather Merge <- Hash Join on birth year <- 2x Seq Scan
    after:     3 ms  Incremental Sort <- Nested Loop on ix_person_birth_year_token

Arabic note: the database runs under the ``C`` collation, so ordering is
byte-wise. That is irrelevant here because the token comparison is equality on
already-normalised text; the fuzzy score itself is computed in Python.
"""

from __future__ import annotations

from alembic import op

revision = "0002_duplicate_indexes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_birth_year_token
            ON person (
                (EXTRACT(YEAR FROM birth_date)),
                (split_part(full_name_normalized, ' ', 1))
            )
            WHERE merged_into_id IS NULL AND birth_date IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_birth_year_second_token
            ON person (
                (EXTRACT(YEAR FROM birth_date)),
                (split_part(full_name_normalized, ' ', 2))
            )
            WHERE merged_into_id IS NULL AND birth_date IS NOT NULL
        """
    )
    # The list endpoints filter out merged rows and sort by name; a covering
    # index keeps the default listing off a sequential scan.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_person_active_name
            ON person (full_name_normalized, id)
            WHERE merged_into_id IS NULL
        """
    )
    op.execute("ANALYZE person")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_person_active_name")
    op.execute("DROP INDEX IF EXISTS ix_person_birth_year_second_token")
    op.execute("DROP INDEX IF EXISTS ix_person_birth_year_token")
