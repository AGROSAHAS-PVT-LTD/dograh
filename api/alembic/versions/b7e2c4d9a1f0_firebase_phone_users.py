"""Add Firebase phone identity to users.

Revision ID: b7e2c4d9a1f0
Revises: a1d4c7e2f9b3
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c4d9a1f0"
down_revision: Union[str, Sequence[str], None] = "a1d4c7e2f9b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("phone_number", sa.String(), nullable=True),
    )
    op.create_index(
        "ix_users_phone_number",
        "users",
        ["phone_number"],
        unique=True,
        postgresql_where=sa.text("phone_number IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_users_phone_number", table_name="users")
    op.drop_column("users", "phone_number")
