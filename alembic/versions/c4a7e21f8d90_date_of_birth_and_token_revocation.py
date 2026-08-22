"""Date of birth and token revocation

Two columns on `users`, added together because they are one deployment.

`date_of_birth` is nullable. Accounts that already exist have no date and
inventing one would be worse than admitting we do not know; new registrations
are required to supply it by the API schema, not by the database, so that the
requirement can be relaxed later for an imported account without a migration.

`token_version` is NOT NULL with a server default of 0, and the default is the
point. Every token in circulation when this deploys carries no version claim
and is read as 0, so the deployment signs nobody out. From the first
revocation onwards the account's version moves ahead of those tokens and they
stop working.

Revision ID: c4a7e21f8d90
Revises: b71e3a90cd45
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a7e21f8d90"
down_revision: str | None = "b71e3a90cd45"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("date_of_birth", sa.Date(), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_column("users", "date_of_birth")
