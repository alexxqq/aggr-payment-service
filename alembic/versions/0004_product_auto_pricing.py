"""Add auto-pricing fields to products table.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "base_amount",
            sa.Numeric(precision=36, scale=18),
            nullable=True,
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "base_currency",
            sa.String(8),
            nullable=True,
            server_default="USD",
        ),
    )
    op.add_column(
        "products",
        sa.Column(
            "auto_pricing_enabled",
            sa.Boolean(),
            nullable=True,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "auto_pricing_enabled")
    op.drop_column("products", "base_currency")
    op.drop_column("products", "base_amount")
