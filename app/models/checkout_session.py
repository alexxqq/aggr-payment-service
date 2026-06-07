"""CheckoutSession model — dynamically generated checkout links for merchants."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class CheckoutSession(Base):
    """Represents a dynamically generated checkout session.

    Merchants can create sessions programmatically to generate unique checkout URLs
    for shopping carts. Each session has a fixed amount and optional redirect URLs.

    Lifecycle: active → used_by_payment_intent | expired
    """

    __tablename__ = "checkout_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # Amount and base currency (USD, EUR, etc — before crypto conversion)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(16), nullable=False)

    # Optional: pre-selected asset and chain (customer can override if not set)
    asset: Mapped[str | None] = mapped_column(String(32), nullable=True)
    chain: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Price locked at session creation (protects merchant from market volatility)
    rate_at_creation: Mapped[Decimal | None] = mapped_column(
        Numeric(36, 18), nullable=True, comment="USD price of selected asset at session creation"
    )

    # Redirect URLs for post-payment flow
    success_redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_redirect_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Merchant-provided metadata (order_id, cart_id, customer_id, etc)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Session expiration
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Track if this session was used
    used_by_payment_intent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
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
