"""Pydantic schemas for the payment options endpoint."""

from pydantic import BaseModel


class PaymentOptionItem(BaseModel):
    option_id: str                     # e.g. "ethereum:ETH" or "arbitrum:USDC"
    product_price_id: str | None       # UUID of the ProductPrice, or None for quick paywall
    chain: str
    chain_display_name: str
    asset: str
    amount: str                        # human-readable decimal string
    transfer_type: str                 # "native" | "erc20"
    token_contract_address: str | None
    token_decimals: int
    estimated_fee_wei: str | None      # None if estimation failed
    estimated_fee_native: str | None   # human-readable ETH string, e.g. "0.000065"
    source: str                        # "rpc" | "fallback" | "error" | "disabled"
    recommended: bool
    executable: bool
    reason: str | None                 # e.g. "lowest_estimated_fee"
    disabled_reason: str | None        # e.g. "token_contract_not_configured"
    pricing_mode: str = "manual"       # "manual" | "auto"
    estimated_fee_usd: str | None = None
    total_estimated_cost_usd: str | None = None


class PaymentOptionsResponse(BaseModel):
    paywall_id: str
    product_name: str | None
    cost_optimization_enabled: bool
    recommended_option_id: str | None
    options: list[PaymentOptionItem]
    pricing_mode: str = "manual"       # "manual" | "auto"
    base_amount: str | None = None
    base_currency: str | None = None
