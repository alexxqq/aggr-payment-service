"""Pydantic schemas for PaymentIntent and PaymentEvent."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


class PaymentIntentCreate(BaseModel):
    asset: str
    chain: str
    amount: str  # decimal string, e.g. "10.50"
    product_price_id: UUID | None = None
    payer_address: str | None = None
    metadata: dict | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str) -> str:
        try:
            d = Decimal(v)
        except InvalidOperation:
            raise ValueError("amount must be a valid decimal number")
        if d <= 0:
            raise ValueError("amount must be positive")
        return v


class PaymentIntentResponse(BaseModel):
    id: UUID
    merchant_id: str
    product_price_id: UUID | None
    asset: str
    chain: str
    amount: str
    status: str
    payer_address: str | None
    recipient_address: str | None
    metadata: dict | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PaymentEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_intent_id: UUID
    event_type: str
    from_status: str | None
    to_status: str | None
    data_json: str | None
    created_at: datetime


_VALID_STATUSES = {"pending", "confirmed", "completed", "failed", "expired"}


class StatusTransitionRequest(BaseModel):
    new_status: str
    data: dict | None = None

    @field_validator("new_status")
    @classmethod
    def validate_new_status(cls, v: str) -> str:
        if v not in _VALID_STATUSES:
            raise ValueError(f"new_status must be one of {sorted(_VALID_STATUSES)}")
        return v
