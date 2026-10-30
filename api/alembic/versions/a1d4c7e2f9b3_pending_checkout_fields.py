"""Track a pending checkout without modifying the active subscription.

Revision ID: a1d4c7e2f9b3
Revises: f2c8a7d4e9b1
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1d4c7e2f9b3"
down_revision: Union[str, Sequence[str], None] = "f2c8a7d4e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organization_subscriptions",
        sa.Column("pending_plan_code", sa.String(), nullable=True),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("pending_currency", sa.String(length=3), nullable=True),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("pending_billing_interval", sa.String(), nullable=True),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("pending_amount_minor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("pending_provider_plan_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    for column in (
        "pending_provider_plan_id",
        "pending_amount_minor",
        "pending_billing_interval",
        "pending_currency",
        "pending_plan_code",
    ):
        op.drop_column("organization_subscriptions", column)
