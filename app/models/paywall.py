"""Paywall model."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

PAYWALL_TYPE_QUICK = "quick"
PAYWALL_TYPE_PRODUCT = "product"


class Paywall(Base):
    __tablename__ = "paywalls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_ids: Mapped[list[str]] = mapped_column(
        ARRAY(UUID(as_uuid=False)), nullable=False, server_default="{}"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Paywall type: "quick" (standalone fixed price) or "product" (linked to a ProductPrice)
    paywall_type: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=PAYWALL_TYPE_QUICK
    )

    # --- Quick paywall price fields (used when paywall_type == "quick") ---
    asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chain: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(36, 18), nullable=True)

    # --- Product paywall link (used when paywall_type == "product") ---
    product_price_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_prices.id", ondelete="SET NULL"),
        nullable=True,
    )

    # --- Auto-pricing fields ---
    auto_payment_options_enabled: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    allowed_chains: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(64)), nullable=True
    )
    allowed_assets: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(32)), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
