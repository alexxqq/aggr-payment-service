"""Add paywall_type and product_price_id to paywalls.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paywalls",
        sa.Column(
            "paywall_type",
            sa.String(16),
            nullable=False,
            server_default="quick",
        ),
    )
    op.add_column(
        "paywalls",
        sa.Column(
            "product_price_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_paywalls_product_price_id",
        "paywalls",
        "product_prices",
        ["product_price_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_paywalls_product_price_id", "paywalls", type_="foreignkey")
    op.drop_column("paywalls", "product_price_id")
    op.drop_column("paywalls", "paywall_type")
