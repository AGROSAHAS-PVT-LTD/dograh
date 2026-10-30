"""Allow one Flutterwave customer to belong to multiple organizations.

Revision ID: f2c8a7d4e9b1
Revises: e7b3d1a9c2f4
Create Date: 2026-10-29
"""

from typing import Sequence, Union

from alembic import op

revision: str = "f2c8a7d4e9b1"
down_revision: Union[str, Sequence[str], None] = "e7b3d1a9c2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "organization_subscriptions_stripe_customer_id_key",
        "organization_subscriptions",
        type_="unique",
    )
    op.drop_constraint(
        "organization_subscriptions_stripe_subscription_id_key",
        "organization_subscriptions",
        type_="unique",
    )
    op.create_index(
        "ix_organization_subscriptions_provider_customer_id",
        "organization_subscriptions",
        ["provider_customer_id"],
    )
    op.create_index(
        "ix_organization_subscriptions_provider_subscription_id",
        "organization_subscriptions",
        ["provider_subscription_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_subscriptions_provider_subscription_id",
        table_name="organization_subscriptions",
    )
    op.drop_index(
        "ix_organization_subscriptions_provider_customer_id",
        table_name="organization_subscriptions",
    )
    op.create_unique_constraint(
        "organization_subscriptions_stripe_customer_id_key",
        "organization_subscriptions",
        ["provider_customer_id"],
    )
    op.create_unique_constraint(
        "organization_subscriptions_stripe_subscription_id_key",
        "organization_subscriptions",
        ["provider_subscription_id"],
    )
