"""Pydantic schemas for Product and ProductPrice."""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID


from pydantic import BaseModel, ConfigDict, field_validator


class ProductCreate(BaseModel):
    """Request body for creating a product. Merchant ID comes from header."""

    name: str
    description: str | None = None
    base_amount: str | None = None  # decimal string for auto-pricing
    base_currency: str = "USD"
    auto_pricing_enabled: bool = False


class ProductUpdate(BaseModel):
    """Request body for partial product update (PATCH semantics)."""

    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    base_amount: str | None = None
    base_currency: str | None = None
    auto_pricing_enabled: bool | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: str
    name: str
    description: str | None
    is_active: bool
    base_amount: Decimal | None = None
    base_currency: str | None = None
    auto_pricing_enabled: bool | None = None
    created_at: datetime
    updated_at: datetime


class ProductPriceCreate(BaseModel):
    """Request body for creating a price on a product."""

    asset: str
    chain: str
    amount: str  # decimal string, e.g. "10.50"

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


class ProductPriceUpdate(BaseModel):
    """Request body for partial price update."""

    is_active: bool | None = None
    amount: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            d = Decimal(v)
        except InvalidOperation:
            raise ValueError("amount must be a valid decimal number")
        if d <= 0:
            raise ValueError("amount must be positive")
        return v


class ProductPriceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    asset: str
    chain: str
    amount: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
