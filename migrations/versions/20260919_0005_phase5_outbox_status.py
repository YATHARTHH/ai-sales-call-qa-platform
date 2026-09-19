"""Phase 5 Transactional Outbox status column and optimized claim index.

Revision ID: 20260919_0005
Revises: 20260919_0004
Create Date: 2026-09-19 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0005"
down_revision: str | None = "20260919_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbox_events") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(32), server_default="PENDING", nullable=False)
        )

    op.drop_index("ix_outbox_unpublished", table_name="outbox_events")
    op.create_index(
        "ix_outbox_claim",
        "outbox_events",
        ["status", "locked_until", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_claim", table_name="outbox_events")
    op.create_index(
        "ix_outbox_unpublished",
        "outbox_events",
        ["published_at", "locked_until", "next_attempt_at"],
    )
    with op.batch_alter_table("outbox_events") as batch_op:
        batch_op.drop_column("status")
