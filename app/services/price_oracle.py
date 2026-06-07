"""Real-time price oracle with CoinGecko API and in-memory cache.

Provides real-time prices for crypto assets with automatic fallback to cached
or safety default values if the API is unavailable.
"""

import asyncio
import logging
import time
from decimal import Decimal

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# CoinGecko API endpoint
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# Map asset symbols to CoinGecko IDs
ASSET_TO_COINGECKO_ID = {
    "ETH": "ethereum",
    "POL": "polygon",
    "USDC": "usd-coin",
    "USDT": "tether",
}


class PriceCache:
    """In-memory cache for asset prices with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl_seconds = ttl_seconds
        self.cache: dict[str, dict] = {}

    def get(self, asset: str) -> Decimal | None:
        """Get cached price if it exists and is fresh."""
        if asset not in self.cache:
            return None
        entry = self.cache[asset]
        if time.time() - entry["updated_at"] > self.ttl_seconds:
            return None
        return entry["price"]

    def set(self, asset: str, price: Decimal) -> None:
        """Store price in cache with current timestamp."""
        self.cache[asset] = {
            "price": price,
            "updated_at": time.time(),
        }


# Global cache instance
_price_cache = PriceCache()


async def get_price(asset: str) -> Decimal:
    """Fetch real-time price for an asset, with fallback to cache/safety defaults.

    Args:
        asset: Asset symbol (e.g., "ETH", "POL", "USDC")

    Returns:
        Price in USD as Decimal.

    Fallback priority:
        1. Live CoinGecko API
        2. Cached price (even if stale)
        3. Safety default from config
    """
    asset_upper = asset.upper()
    settings = get_settings()

    # Step 1: Try live API
    try:
        price = await _fetch_from_coingecko(asset_upper, settings)
        if price is not None:
            _price_cache.set(asset_upper, price)
            return price
    except Exception as exc:
        logger.warning("CoinGecko API call failed for %s: %s", asset_upper, exc)

    # Step 2: Try cached price
    cached_price = _price_cache.get(asset_upper)
    if cached_price is not None:
        logger.info("Using cached price for %s: $%s", asset_upper, cached_price)
        return cached_price

    # Step 3: Use safety default
    fallback_price = _get_safety_default(asset_upper, settings)
    logger.critical(
        "API and cache unavailable for %s, using safety default: $%s",
        asset_upper,
        fallback_price,
    )
    return fallback_price


async def _fetch_from_coingecko(asset: str, settings) -> Decimal | None:
    """Fetch price from CoinGecko API."""
    coingecko_id = ASSET_TO_COINGECKO_ID.get(asset)
    if coingecko_id is None:
        logger.warning("Asset %s not mapped to CoinGecko ID", asset)
        return None

    api_key = settings.coingecko_api_key
    if not api_key:
        logger.warning("COINGECKO_API_KEY not configured")
        return None

    url = f"{COINGECKO_API_URL}/simple/price"
    params = {
        "ids": coingecko_id,
        "vs_currencies": "usd",
    }
    headers = {
        "x-cg-demo-api-key": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params, headers=headers)
            if response.status_code == 200:
                data = response.json()
                price_usd = data.get(coingecko_id, {}).get("usd")
                if price_usd is not None:
                    price = Decimal(str(price_usd))
                    logger.debug("Fetched %s price from CoinGecko: $%s", asset, price)
                    return price
            else:
                logger.warning(
                    "CoinGecko API returned status %d for %s", response.status_code, asset
                )
    except asyncio.TimeoutError:
        logger.warning("CoinGecko API timeout for %s", asset)
    except Exception as exc:
        logger.error("Error fetching price from CoinGecko for %s: %s", asset, exc)

    return None


def _get_safety_default(asset: str, settings) -> Decimal:
    """Get safety default price from config."""
    defaults = {
        "ETH": Decimal(settings.price_fallback_eth_usd),
        "POL": Decimal(settings.price_fallback_pol_usd),
        "USDC": Decimal(settings.price_fallback_usdc_usd),
        "USDT": Decimal(settings.price_fallback_usdt_usd),
    }
    return defaults.get(asset, Decimal("1.00"))
