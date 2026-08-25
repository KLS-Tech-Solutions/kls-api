"""State, country, and an optional phone number

Two additive columns and one loosened constraint.

`state` and `country` are nullable because every existing row predates them and
there is no honest default — "India" would be a guess written into the record
as though it were fact.

Making `phone` nullable is the interesting half. It is a widening change, so
the upgrade is safe and instant even on a large table: no rewrite, no scan, no
lock worth worrying about. **The downgrade is not symmetric.** By the time it
runs there may be rows with a NULL phone, and `SET NOT NULL` on a column
containing NULLs fails outright. Rather than let a rollback die halfway, the
downgrade fills those rows with an empty string first — which is what the
column would have held anyway, since that is exactly what the old code wrote
for admins and for closed accounts.

Revision ID: d7b3f0a91c26
Revises: c4a7e21f8d90
Create Date: 2026-08-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7b3f0a91c26"
down_revision: str | None = "c4a7e21f8d90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("state", sa.String(length=80), nullable=True))
    op.add_column("users", sa.Column("country", sa.String(length=80), nullable=True))

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "phone",
            existing_type=sa.String(length=20),
            nullable=True,
        )


def downgrade() -> None:
    # Rows added since the upgrade may hold NULL; NOT NULL would reject them.
    op.execute("UPDATE users SET phone = '' WHERE phone IS NULL")

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "phone",
            existing_type=sa.String(length=20),
            nullable=False,
        )

    op.drop_column("users", "country")
    op.drop_column("users", "state")
