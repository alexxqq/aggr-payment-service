"""Add rate_at_creation fields for price oracle.

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add rate_at_creation to payment_intents
    op.add_column(
        "payment_intents",
        sa.Column(
            "rate_at_creation",
            sa.Numeric(precision=36, scale=18),
            nullable=True,
            comment="USD price of asset at checkout initialization",
        ),
    )

    # Add rate_at_creation to checkout_sessions
    op.add_column(
        "checkout_sessions",
        sa.Column(
            "rate_at_creation",
            sa.Numeric(precision=36, scale=18),
            nullable=True,
            comment="USD price of selected asset at session creation",
        ),
    )


def downgrade() -> None:
    op.drop_column("checkout_sessions", "rate_at_creation")
    op.drop_column("payment_intents", "rate_at_creation")
