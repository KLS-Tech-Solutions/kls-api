"""Multiple internships, editable fee, account deletion

Three independent changes that ship together:

* `platform_settings` — runtime operational values, currently the certificate
  fee, so a super admin can change the price without a deploy.
* `users.deleted_at` — marks an account closed by its holder. A soft delete,
  because issued certificates must stay publicly verifiable.
* `certificates.student_name` — snapshots the recipient at issue and is
  backfilled from the user row, so scrubbing a closed account cannot make a
  paid-for credential verify as "Deleted user".

Revision ID: 3c91a7de40b2
Revises: 02584f9e6f21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3c91a7de40b2"
down_revision: str | None = "02584f9e6f21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_settings_key"), "platform_settings", ["key"], unique=True
    )

    op.add_column(
        "users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "certificates", sa.Column("student_name", sa.String(length=100), nullable=True)
    )

    # Backfill the snapshot for certificates issued before this column existed.
    # Doing it now, while every user row still holds a real name, is the only
    # moment this is possible.
    op.execute(
        """
        UPDATE certificates
        SET student_name = (
            SELECT full_name FROM users WHERE users.id = certificates.student_id
        )
        WHERE student_name IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("certificates", "student_name")
    op.drop_column("users", "deleted_at")
    op.drop_index(op.f("ix_platform_settings_key"), table_name="platform_settings")
    op.drop_table("platform_settings")
