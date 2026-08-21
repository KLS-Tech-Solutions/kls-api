"""Record who last edited a study-notes chapter

Chapter management moved from super-admin-only to any admin. While one person
could edit the notes, "who changed this" was answerable by elimination; with a
team it is not.

`updated_by` is nullable and `ON DELETE SET NULL` — an admin leaving must not
take the teaching material with them. Existing rows get NULL, which the console
renders as "—" rather than guessing.

This is the **only** schema change needed for the analytics, SEO, testing and CI
work. None of those store anything: Mixpanel holds its own events, SEO is
static output, and the tests and workflows touch no tables at all.

Revision ID: b71e3a90cd45
Revises: 9d4f1c7ab653
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b71e3a90cd45"
down_revision: str | None = "9d4f1c7ab653"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Batch mode because SQLite cannot add a foreign key to an existing table
    # in place; on PostgreSQL this compiles to a plain ALTER.
    with op.batch_alter_table("learning_chapters") as batch:
        batch.add_column(sa.Column("updated_by", sa.Uuid(), nullable=True))
        batch.create_foreign_key(
            "fk_learning_chapters_updated_by",
            "users",
            ["updated_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_chapters") as batch:
        batch.drop_constraint("fk_learning_chapters_updated_by", type_="foreignkey")
        batch.drop_column("updated_by")
