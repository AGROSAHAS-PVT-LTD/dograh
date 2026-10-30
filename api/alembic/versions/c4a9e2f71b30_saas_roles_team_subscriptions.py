"""SaaS organization roles, invitations, and subscriptions.

Revision ID: c4a9e2f71b30
Revises: 3a7b91c5d402, d6a83e2b19f0
Create Date: 2026-10-28
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4a9e2f71b30"
down_revision: Union[str, Sequence[str], None] = (
    "3a7b91c5d402",
    "d6a83e2b19f0",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    organization_role = postgresql.ENUM(
        "owner", "admin", "member", name="organization_role", create_type=False
    )
    invitation_status = postgresql.ENUM(
        "pending",
        "accepted",
        "revoked",
        "expired",
        name="organization_invitation_status",
        create_type=False,
    )
    subscription_status = postgresql.ENUM(
        "trialing",
        "active",
        "past_due",
        "canceled",
        "unpaid",
        "incomplete",
        "incomplete_expired",
        "paused",
        name="organization_subscription_status",
        create_type=False,
    )

    bind = op.get_bind()
    organization_role.create(bind, checkfirst=True)
    invitation_status.create(bind, checkfirst=True)
    subscription_status.create(bind, checkfirst=True)

    op.add_column(
        "organization_users",
        sa.Column(
            "role",
            organization_role,
            nullable=False,
            server_default=sa.text("'member'"),
        ),
    )
    # Existing memberships predate roles. Treat the existing members as owners
    # so no current user loses access after the migration.
    op.execute("UPDATE organization_users SET role = 'owner'")

    op.create_table(
        "organization_invitations",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column(
            "role",
            organization_role,
            nullable=False,
            server_default=sa.text("'member'"),
        ),
        sa.Column("token_hash", sa.String(), nullable=False),
        sa.Column(
            "status",
            invitation_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("invited_by", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("uuid"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_organization_invitations_org",
        "organization_invitations",
        ["organization_id"],
    )
    op.create_index(
        "ix_organization_invitations_email",
        "organization_invitations",
        ["email"],
    )

    op.create_table(
        "organization_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("plan_code", sa.String(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(), nullable=True),
        sa.Column(
            "status",
            subscription_status,
            nullable=False,
            server_default=sa.text("'trialing'"),
        ),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("trial_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("organization_id"),
        sa.UniqueConstraint("stripe_customer_id"),
        sa.UniqueConstraint("stripe_subscription_id"),
    )

    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.UniqueConstraint("event_id"),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_table("organization_subscriptions")
    op.drop_index(
        "ix_organization_invitations_email", table_name="organization_invitations"
    )
    op.drop_index(
        "ix_organization_invitations_org", table_name="organization_invitations"
    )
    op.drop_table("organization_invitations")
    op.drop_column("organization_users", "role")

    for enum_name in (
        "organization_invitation_status",
        "organization_subscription_status",
        "organization_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
