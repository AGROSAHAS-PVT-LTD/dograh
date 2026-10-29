"""Switch SaaS billing from Stripe to Flutterwave.

Revision ID: e7b3d1a9c2f4
Revises: c4a9e2f71b30
Create Date: 2026-10-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b3d1a9c2f4"
down_revision: Union[str, Sequence[str], None] = "c4a9e2f71b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("stripe_events", "billing_events")
    op.alter_column(
        "billing_events", "event_id", new_column_name="event_key"
    )
    op.add_column(
        "billing_events",
        sa.Column(
            "provider",
            sa.String(),
            nullable=False,
            server_default=sa.text("'flutterwave'"),
        ),
    )

    op.alter_column(
        "organization_subscriptions",
        "stripe_customer_id",
        new_column_name="provider_customer_id",
    )
    op.alter_column(
        "organization_subscriptions",
        "stripe_subscription_id",
        new_column_name="provider_subscription_id",
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column(
            "provider",
            sa.String(),
            nullable=False,
            server_default=sa.text("'flutterwave'"),
        ),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("provider_plan_id", sa.String(), nullable=True),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'USD'"),
        ),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column(
            "billing_interval",
            sa.String(),
            nullable=False,
            server_default=sa.text("'monthly'"),
        ),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("amount_minor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "organization_subscriptions",
        sa.Column("checkout_tx_ref", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_organization_subscriptions_provider_plan_id",
        "organization_subscriptions",
        ["provider_plan_id"],
    )
    op.create_index(
        "ix_organization_subscriptions_checkout_tx_ref",
        "organization_subscriptions",
        ["checkout_tx_ref"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_subscriptions_checkout_tx_ref",
        table_name="organization_subscriptions",
    )
    op.drop_index(
        "ix_organization_subscriptions_provider_plan_id",
        table_name="organization_subscriptions",
    )
    for column in (
        "checkout_tx_ref",
        "amount_minor",
        "billing_interval",
        "currency",
        "provider_plan_id",
        "provider",
    ):
        op.drop_column("organization_subscriptions", column)
    op.alter_column(
        "organization_subscriptions",
        "provider_subscription_id",
        new_column_name="stripe_subscription_id",
    )
    op.alter_column(
        "organization_subscriptions",
        "provider_customer_id",
        new_column_name="stripe_customer_id",
    )

    op.drop_column("billing_events", "provider")
    op.alter_column("billing_events", "event_key", new_column_name="event_id")
    op.rename_table("billing_events", "stripe_events")
