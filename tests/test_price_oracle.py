"""Tests for the PriceOracle service."""

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.price_oracle import (
    get_price,
    _fetch_from_coingecko,
    _get_safety_default,
    PriceCache,
    ASSET_TO_COINGECKO_ID,
)


class TestPriceCache:
    """Tests for PriceCache."""

    def test_cache_set_and_get(self):
        """Test setting and getting a price from cache."""
        cache = PriceCache(ttl_seconds=60)
        price = Decimal("2500.00")
        cache.set("ETH", price)
        assert cache.get("ETH") == price

    def test_cache_expiration(self):
        """Test that cached prices expire after TTL."""
        cache = PriceCache(ttl_seconds=1)
        cache.set("ETH", Decimal("2500.00"))
        # Price should be available immediately
        assert cache.get("ETH") == Decimal("2500.00")
        # After TTL expires, return None
        import time
        time.sleep(1.1)
        assert cache.get("ETH") is None

    def test_cache_nonexistent_key(self):
        """Test getting a non-existent key from cache."""
        cache = PriceCache()
        assert cache.get("NONEXISTENT") is None


@pytest.mark.asyncio
async def test_get_price_live_api():
    """Test fetching price from live CoinGecko API."""
    with patch("app.services.price_oracle._fetch_from_coingecko") as mock_fetch:
        mock_fetch.return_value = Decimal("2500.00")
        price = await get_price("ETH")
        assert price == Decimal("2500.00")
        mock_fetch.assert_called_once()


@pytest.mark.asyncio
async def test_get_price_uses_cache_on_api_failure():
    """Test that cache is used when API fails."""
    with patch("app.services.price_oracle._fetch_from_coingecko") as mock_fetch:
        with patch("app.services.price_oracle._price_cache") as mock_cache:
            # First call succeeds and caches
            mock_fetch.return_value = Decimal("2500.00")
            mock_cache.get.return_value = None
            price1 = await get_price("ETH")
            assert price1 == Decimal("2500.00")

            # Second call fails but cache has value
            mock_fetch.side_effect = Exception("API error")
            mock_cache.get.return_value = Decimal("2450.00")
            price2 = await get_price("ETH")
            assert price2 == Decimal("2450.00")


@pytest.mark.asyncio
async def test_get_price_falls_back_to_safety_default():
    """Test fallback to safety default when API and cache both fail."""
    with patch("app.services.price_oracle._fetch_from_coingecko") as mock_fetch:
        with patch("app.services.price_oracle._price_cache") as mock_cache:
            mock_fetch.side_effect = Exception("API error")
            mock_cache.get.return_value = None
            price = await get_price("ETH")
            # Should return safety default
            assert price == Decimal("2500")


@pytest.mark.asyncio
async def test_fetch_from_coingecko_success(aiohttp_mock):
    """Test successful CoinGecko API call."""
    settings_mock = MagicMock()
    settings_mock.coingecko_api_key = "test-key"

    aiohttp_mock.get(
        "https://api.coingecko.com/api/v3/simple/price",
        payload={"ethereum": {"usd": 2500.00}},
    )

    price = await _fetch_from_coingecko("ETH", settings_mock)
    assert price == Decimal("2500.00")


@pytest.mark.asyncio
async def test_fetch_from_coingecko_missing_api_key():
    """Test that missing API key returns None."""
    settings_mock = MagicMock()
    settings_mock.coingecko_api_key = ""

    price = await _fetch_from_coingecko("ETH", settings_mock)
    assert price is None


@pytest.mark.asyncio
async def test_fetch_from_coingecko_unmapped_asset():
    """Test that unmapped assets return None."""
    settings_mock = MagicMock()
    settings_mock.coingecko_api_key = "test-key"

    price = await _fetch_from_coingecko("UNKNOWN", settings_mock)
    assert price is None


def test_get_safety_default():
    """Test safety default values."""
    settings_mock = MagicMock()
    settings_mock.price_fallback_eth_usd = "2500"
    settings_mock.price_fallback_pol_usd = "0.076"
    settings_mock.price_fallback_usdc_usd = "1.00"
    settings_mock.price_fallback_usdt_usd = "1.00"

    assert _get_safety_default("ETH", settings_mock) == Decimal("2500")
    assert _get_safety_default("POL", settings_mock) == Decimal("0.076")
    assert _get_safety_default("USDC", settings_mock) == Decimal("1.00")
    assert _get_safety_default("USDT", settings_mock) == Decimal("1.00")
    # Unknown asset defaults to 1.00
    assert _get_safety_default("UNKNOWN", settings_mock) == Decimal("1.00")


def test_asset_to_coingecko_id_mapping():
    """Test that all supported assets are mapped."""
    assert "ETH" in ASSET_TO_COINGECKO_ID
    assert "POL" in ASSET_TO_COINGECKO_ID
    assert "USDC" in ASSET_TO_COINGECKO_ID
    assert "USDT" in ASSET_TO_COINGECKO_ID


@pytest.mark.asyncio
async def test_get_price_stablecoin():
    """Test fetching stablecoin price."""
    with patch("app.services.price_oracle._fetch_from_coingecko") as mock_fetch:
        mock_fetch.return_value = Decimal("1.00")
        price = await get_price("USDC")
        assert price == Decimal("1.00")
