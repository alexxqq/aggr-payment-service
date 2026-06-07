"""AnalyticsSnapshot model — pre-computed merchant analytics summaries."""

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AnalyticsSnapshot(Base):
    """Daily analytics snapshot per merchant.

    Computed by a background job (not in MVP scope).
    Read-only from the API perspective.
    """

    __tablename__ = "analytics_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    merchant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    total_intents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_intents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_intents: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Total volume in USD equivalent (approximate, for display only)
    total_volume_usd: Mapped[str] = mapped_column(
        Numeric(36, 2).with_variant(String(78), "postgresql"),
        nullable=False,
        default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
