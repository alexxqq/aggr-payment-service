"""Pydantic schemas for Paywall."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

PAYWALL_TYPE_QUICK = "quick"
PAYWALL_TYPE_PRODUCT = "product"


class PaywallCreate(BaseModel):
    name: str
    description: str | None = None
    paywall_type: str = PAYWALL_TYPE_QUICK

    # Quick paywall fields
    asset: str | None = None
    chain: str | None = None
    amount: Decimal | None = None

    # Product paywall fields
    product_price_id: UUID | None = None
    product_ids: list[UUID] | None = None

    # Auto-pricing fields
    auto_payment_options_enabled: bool = False
    allowed_chains: list[str] | None = None
    allowed_assets: list[str] | None = None

    @model_validator(mode="after")
    def validate_type_fields(self) -> "PaywallCreate":
        if self.paywall_type == PAYWALL_TYPE_QUICK:
            missing = [f for f in ("asset", "chain", "amount") if not getattr(self, f)]
            if missing:
                raise ValueError(
                    f"Quick paywall requires: {', '.join(missing)}"
                )
        elif self.paywall_type == PAYWALL_TYPE_PRODUCT:
            # Product paywall requires either product_price_id OR auto_payment_options_enabled
            if not self.product_price_id and not self.auto_payment_options_enabled:
                raise ValueError(
                    "Product paywall requires product_price_id or auto_payment_options_enabled=true"
                )
        else:
            raise ValueError(f"paywall_type must be '{PAYWALL_TYPE_QUICK}' or '{PAYWALL_TYPE_PRODUCT}'")
        return self


class PaywallUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None

    # Quick paywall price fields
    asset: str | None = None
    chain: str | None = None
    amount: Decimal | None = None

    # Product paywall link
    product_price_id: UUID | None = None

    # Auto-pricing fields
    auto_payment_options_enabled: bool | None = None
    allowed_chains: list[str] | None = None
    allowed_assets: list[str] | None = None


class PaywallResponse(BaseModel):
    """Merchant-facing and public response.

    asset/chain/amount are always resolved — from the paywall directly for
    quick paywalls, or from the linked ProductPrice for product paywalls.
    """
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    merchant_id: str
    name: str
    description: str | None
    is_active: bool
    paywall_type: str
    product_price_id: UUID | None
    # Resolved price — always populated for usable paywalls
    asset: str | None
    chain: str | None
    amount: Decimal | None
    # Auto-pricing fields
    auto_payment_options_enabled: bool | None = None
    allowed_chains: list[str] | None = None
    allowed_assets: list[str] | None = None
    created_at: datetime
    updated_at: datetime
