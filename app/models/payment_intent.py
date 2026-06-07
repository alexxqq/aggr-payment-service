"""PaymentIntent model."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PaymentIntent(Base):
    """Represents a payment request from a customer to a merchant.

    Lifecycle: pending → confirmed → completed | failed | expired
    Blockchain execution is handled by Blockchain Core service.
    """

    __tablename__ = "payment_intents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    product_price_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("product_prices.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Asset and chain are denormalized for audit history
    asset: Mapped[str] = mapped_column(String(32), nullable=False)
    chain: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(36, 18), nullable=False)
    # Price locked at creation time (protects merchant from market volatility)
    rate_at_creation: Mapped[Decimal | None] = mapped_column(
        Numeric(36, 18), nullable=True, comment="USD price of asset at checkout initialization"
    )
    # Status: pending | confirmed | completed | failed | expired
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    # Payer wallet address (provided by customer at checkout)
    payer_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Recipient wallet from merchant payout config (sourced from User Service)
    recipient_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Checkout metadata (JSON-serializable extra data)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
