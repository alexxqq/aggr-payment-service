"""Schemas for checkout session creation and responses."""

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class CreateCheckoutSessionRequest(BaseModel):
    """Merchant request to create a dynamically-generated checkout session.

    Used for low-code e-commerce integration: merchant provides amount + currency,
    we return a unique checkout URL.
    """

    amount: Decimal = Field(
        ..., gt=Decimal("0"), description="Amount in base currency (USD, EUR, etc)"
    )
    currency: str = Field(
        ..., min_length=3, max_length=16, description="ISO currency code (USD, EUR, GBP)"
    )

    # Optional: pre-select asset and chain (customer can override in checkout)
    asset: Optional[str] = Field(
        None, max_length=32, description="Pre-selected crypto asset (USDC, ETH, MATIC)"
    )
    chain: Optional[str] = Field(
        None, max_length=64, description="Pre-selected blockchain (ethereum, arbitrum, polygon)"
    )

    # Redirect URLs for post-payment flow
    success_redirect_url: Optional[HttpUrl] = Field(
        None, description="Redirect customer here after successful payment"
    )
    cancel_redirect_url: Optional[HttpUrl] = Field(
        None, description="Redirect customer here if they cancel checkout"
    )

    # Merchant metadata (JSON-serializable)
    metadata: Optional[dict] = Field(
        None, description="Merchant-provided metadata (order_id, customer_id, etc)"
    )

    expires_in_minutes: int = Field(
        default=60, ge=5, le=10080, description="Session expiration time in minutes (5m - 7d)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "amount": 99.99,
                "currency": "USD",
                "asset": "USDC",
                "chain": "arbitrum",
                "success_redirect_url": "https://example.com/order/success",
                "cancel_redirect_url": "https://example.com/checkout",
                "metadata": {"order_id": "ORD-12345", "customer_id": "cust_abc"},
                "expires_in_minutes": 60,
            }
        }


class CheckoutSessionResponse(BaseModel):
    """Response containing the created checkout session and its public URL."""

    session_id: str = Field(..., description="Unique session identifier")
    checkout_url: str = Field(
        ..., description="Public URL for customer to complete checkout"
    )
    amount: str = Field(..., description="Amount in base currency")
    currency: str = Field(..., description="Base currency")
    asset: Optional[str] = Field(None, description="Pre-selected asset (if any)")
    chain: Optional[str] = Field(None, description="Pre-selected chain (if any)")
    expires_at: str = Field(..., description="ISO timestamp when session expires")
    created_at: str = Field(..., description="ISO timestamp of creation")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_abc123def456",
                "checkout_url": "https://checkout.example.com/checkout/sess_abc123def456",
                "amount": "99.99",
                "currency": "USD",
                "asset": "USDC",
                "chain": "arbitrum",
                "expires_at": "2026-06-07T13:00:00Z",
                "created_at": "2026-06-07T12:00:00Z",
            }
        }
