"""Quote service — converts base fiat amounts to crypto amounts using live PriceOracle."""

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.services.price_oracle import get_price

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QuoteResult:
    """Result of converting a fiat amount to crypto."""

    asset: str  # e.g. "ETH", "USDC"
    crypto_amount: Decimal  # amount in asset units, properly quantized
    rate_used: Decimal  # price of 1 unit of asset in USD
    rate_source: str = "price_oracle"


async def get_quote(
    base_amount: Decimal,
    base_currency: str,
    asset: str,
) -> QuoteResult | None:
    """Convert a base fiat amount to crypto using live prices from PriceOracle.

    Args:
        base_amount: amount in fiat (e.g. Decimal("20.00") for $20 USD)
        base_currency: fiat currency code (e.g. "USD")
        asset: target crypto asset (e.g. "ETH", "USDC", "POL")

    Returns:
        QuoteResult with crypto_amount and rate_used, or None if price unavailable.
    """
    if base_currency.upper() != "USD":
        logger.warning("Only USD quotes are supported, got %s", base_currency)
        return None

    # Fetch live price from PriceOracle
    try:
        price_usd = await get_price(asset)
    except Exception as exc:
        logger.warning("Failed to fetch price for %s: %s", asset, exc)
        return None

    if price_usd is None or price_usd <= 0:
        return None

    # Calculate crypto amount: base_amount (USD) / price_per_unit (USD)
    crypto_amount = base_amount / price_usd

    # Quantize based on asset precision:
    # - USDC/USDT: 6 decimal places (ERC-20 standard)
    # - ETH/POL: 18 decimal places (blockchain standard)
    if asset.upper() in {"USDC", "USDT"}:
        quantum = Decimal("0.000001")
    else:
        quantum = Decimal("0.000000000000000001")

    crypto_amount = crypto_amount.quantize(quantum, rounding=ROUND_HALF_UP)

    logger.debug(
        "Quote: %s %s = %s %s (price: $%s)",
        base_amount,
        base_currency,
        crypto_amount,
        asset,
        price_usd,
    )

    return QuoteResult(
        asset=asset.upper(),
        crypto_amount=crypto_amount,
        rate_used=price_usd,
        rate_source="price_oracle",
    )
