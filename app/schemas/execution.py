"""Schemas for execution request payloads sent to Blockchain Core."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class ExecutionRequestPayload(BaseModel):
    """Data contract for Blockchain Core to execute a payment."""

    payment_intent_id: UUID
    merchant_id: str
    chain: str
    asset: str
    amount: str
    payer_address: str | None
    recipient_address: str | None  # payout wallet; None if unavailable
    metadata: dict | None
    intent_created_at: datetime
