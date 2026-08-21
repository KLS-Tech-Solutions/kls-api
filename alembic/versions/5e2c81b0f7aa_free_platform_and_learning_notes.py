"""Free platform, learning notes, private storage

The go-to-market changed: KLS Academy is open source and free, so the payment
step is gone rather than disabled. Alongside that:

* `payments` and `platform_settings` are dropped. The only setting was the
  certificate fee, and there is no fee.
* `certificates.payment_id` goes with them. The certificate is now issued when
  the final task is approved.
* `learning_chapters` and `chapter_reads` arrive — chapter-wise study notes per
  domain, which students read before starting the tasks.

`created_at` and `updated_at` carry a `server_default`. `TimestampMixin` has no
Python-side default, so SQLAlchemy never sends those columns on insert and the
database has to fill them — without the default, every insert fails the NOT NULL
check. Migration `9d4f1c7ab653` repairs databases that ran the first version of
this file.

**Existing document numbers are left alone.** They were sequential and are now
random, but a certificate number is a public credential: rewriting the numbers
already issued would break every verification link that has been shared. New
documents get random numbers; old ones keep theirs.

Revision ID: 5e2c81b0f7aa
Revises: 3c91a7de40b2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5e2c81b0f7aa"
down_revision: str | None = "3c91a7de40b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- learning notes ---------------------------------------------------
    op.create_table(
        "learning_chapters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("domain_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("order_number", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), nullable=False),
        sa.Column("pdf_url", sa.String(length=500), nullable=True),
        sa.Column("pdf_filename", sa.String(length=255), nullable=True),
        sa.Column("pdf_size_bytes", sa.Integer(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["domain_id"], ["internship_domains.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain_id", "order_number", name="uq_chapter_position"),
    )
    op.create_index(
        op.f("ix_learning_chapters_domain_id"),
        "learning_chapters",
        ["domain_id"],
    )

    op.create_table(
        "chapter_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("chapter_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["chapter_id"], ["learning_chapters.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "chapter_id", name="uq_chapter_read"),
    )
    op.create_index(
        op.f("ix_chapter_reads_student_id"), "chapter_reads", ["student_id"]
    )
    op.create_index(
        op.f("ix_chapter_reads_chapter_id"), "chapter_reads", ["chapter_id"]
    )

    # --- payments are gone ------------------------------------------------
    # The foreign key goes before the table it points at.
    with op.batch_alter_table("certificates") as batch:
        batch.drop_column("payment_id")

    op.drop_table("payments")

    # The only platform setting was the certificate fee.
    op.drop_index(op.f("ix_platform_settings_key"), table_name="platform_settings")
    op.drop_table("platform_settings")


def downgrade() -> None:
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("updated_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_platform_settings_key"), "platform_settings", ["key"], unique=True
    )

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), nullable=True),
        sa.Column("razorpay_order_id", sa.String(length=100), nullable=True),
        sa.Column("transaction_id", sa.String(length=100), nullable=True),
        sa.Column("signature", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_status", sa.String(length=20), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["enrollments.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # The indexes have to come back too — the initial migration's downgrade
    # drops them by name, and fails if they are missing.
    op.create_index(
        op.f("ix_payments_student_id"), "payments", ["student_id"]
    )
    op.create_index(
        op.f("ix_payments_razorpay_order_id"), "payments", ["razorpay_order_id"]
    )
    op.create_index(
        op.f("ix_payments_transaction_id"), "payments", ["transaction_id"]
    )
    op.create_index(
        op.f("ix_payments_payment_status"), "payments", ["payment_status"]
    )

    with op.batch_alter_table("certificates") as batch:
        batch.add_column(sa.Column("payment_id", sa.Uuid(), nullable=True))

    op.drop_index(op.f("ix_chapter_reads_chapter_id"), table_name="chapter_reads")
    op.drop_index(op.f("ix_chapter_reads_student_id"), table_name="chapter_reads")
    op.drop_table("chapter_reads")
    op.drop_index(
        op.f("ix_learning_chapters_domain_id"), table_name="learning_chapters"
    )
    op.drop_table("learning_chapters")
