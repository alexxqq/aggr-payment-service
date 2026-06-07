"""Add asset/chain/amount price fields to paywalls table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("paywalls", sa.Column("asset", sa.String(32), nullable=True))
    op.add_column("paywalls", sa.Column("chain", sa.String(64), nullable=True))
    op.add_column("paywalls", sa.Column("amount", sa.Numeric(36, 18), nullable=True))


def downgrade() -> None:
    op.drop_column("paywalls", "amount")
    op.drop_column("paywalls", "chain")
    op.drop_column("paywalls", "asset")
