"""Repair the timestamp defaults on the learning-notes tables

The first version of `5e2c81b0f7aa` created `learning_chapters` and
`chapter_reads` with `created_at` / `updated_at` marked NOT NULL but with **no
column default**.

`TimestampMixin` sets `server_default=func.now()` and no Python-side default, so
SQLAlchemy never sends those columns on an insert — the database is expected to
fill them. Without the default, every insert failed the NOT NULL check, which is
what made "Add chapter" return a 500.

The test suite did not catch it because `tests/conftest.py` builds the schema
with `Base.metadata.create_all()`, which reads the *models* — where the default
is present — rather than replaying the migrations. `tests/test_migrations.py`
now closes that gap.

Safe to run on a database created by either version of that migration: setting a
default that is already correct is a no-op.

Revision ID: 9d4f1c7ab653
Revises: 5e2c81b0f7aa
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d4f1c7ab653"
down_revision: str | None = "5e2c81b0f7aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("learning_chapters", "chapter_reads")
COLUMNS = ("created_at", "updated_at")


def upgrade() -> None:
    bind = op.get_bind()

    # SQLite cannot ALTER a column default in place; batch mode rebuilds the
    # table instead. Postgres does it directly.
    if bind.dialect.name == "sqlite":
        for table in TABLES:
            with op.batch_alter_table(table) as batch:
                for column in COLUMNS:
                    batch.alter_column(
                        column,
                        existing_type=sa.DateTime(timezone=True),
                        existing_nullable=False,
                        server_default=sa.text("(CURRENT_TIMESTAMP)"),
                    )
        return

    for table in TABLES:
        # Backfill anything that slipped in null before fixing the default.
        # There should be none — an insert without a value failed outright —
        # but a row inserted by hand could have one.
        for column in COLUMNS:
            op.execute(
                f"UPDATE {table} SET {column} = CURRENT_TIMESTAMP "
                f"WHERE {column} IS NULL"
            )
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )


def downgrade() -> None:
    bind = op.get_bind()

    if bind.dialect.name == "sqlite":
        for table in TABLES:
            with op.batch_alter_table(table) as batch:
                for column in COLUMNS:
                    batch.alter_column(
                        column,
                        existing_type=sa.DateTime(timezone=True),
                        existing_nullable=False,
                        server_default=None,
                    )
        return

    for table in TABLES:
        for column in COLUMNS:
            op.alter_column(
                table,
                column,
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                server_default=None,
            )
