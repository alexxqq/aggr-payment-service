"""Add auto-options fields to paywalls table.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "paywalls",
        sa.Column(
            "auto_payment_options_enabled",
            sa.Boolean(),
            nullable=True,
            server_default="false",
        ),
    )
    op.add_column(
        "paywalls",
        sa.Column(
            "allowed_chains",
            postgresql.ARRAY(sa.String(64)),
            nullable=True,
        ),
    )
    op.add_column(
        "paywalls",
        sa.Column(
            "allowed_assets",
            postgresql.ARRAY(sa.String(32)),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("paywalls", "allowed_assets")
    op.drop_column("paywalls", "allowed_chains")
    op.drop_column("paywalls", "auto_payment_options_enabled")
