"""Persist the weighted score the gate decided on.

The engine computed an overall weighted score but only the check-level scores were stored, so
dashboards and audits had to recompute an unweighted mean that could disagree with the number the
gate actually used. Storing it makes the decision reproducible from the record alone.

Revision ID: 20260919_0006
Revises: 20260919_0005
Create Date: 2026-09-19 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_0006"
down_revision: str | None = "20260919_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("gate_decisions") as batch_op:
        batch_op.add_column(sa.Column("overall_score", sa.Float(), nullable=True))

    # Reporting queries filter by tenant window and status; decided_at leads the index because
    # every dashboard query is bounded by a date range first.
    op.create_index(
        "ix_gate_decisions_reporting",
        "gate_decisions",
        ["decided_at", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_gate_decisions_reporting", table_name="gate_decisions")
    with op.batch_alter_table("gate_decisions") as batch_op:
        batch_op.drop_column("overall_score")
