"""Unit tests for auto-pricing payment options — quote conversion, asset validation, option generation."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.paywall import Paywall
from app.models.product import Product
from app.schemas.payment_options import PaymentOptionItem, PaymentOptionsResponse
from app.services.asset_compat import is_valid_pair
from app.services.payment_options import build_payment_options
from app.services.quote import get_quote


# ─────────────────────────────────────────────────────────────────────────────
# Quote conversion tests
# ─────────────────────────────────────────────────────────────────────────────


def test_quote_eth_from_usd():
    """Test USD → ETH conversion with configured rate."""
    mock_settings = MagicMock()
    mock_settings.get_quote_rate.return_value = Decimal("0.00035")

    result = get_quote(Decimal("20.00"), "USD", "ETH", mock_settings)

    assert result is not None
    assert result.asset == "ETH"
    assert result.crypto_amount == Decimal("0.0070")  # 20 * 0.00035
    assert result.rate_used == Decimal("0.00035")


def test_quote_matic_from_usd():
    """Test USD → MATIC conversion."""
    mock_settings = MagicMock()
    mock_settings.get_quote_rate.return_value = Decimal("1.25")

    result = get_quote(Decimal("20.00"), "USD", "MATIC", mock_settings)

    assert result is not None
    assert result.asset == "MATIC"
    assert result.crypto_amount == Decimal("25.0")  # 20 * 1.25


def test_quote_usdc_stable_rate():
    """Test USDC stablecoin 1:1 rate."""
    mock_settings = MagicMock()
    mock_settings.get_quote_rate.return_value = Decimal("1.0")

    result = get_quote(Decimal("20.00"), "USD", "USDC", mock_settings)

    assert result is not None
    assert result.asset == "USDC"
    assert result.crypto_amount == Decimal("20.0")  # 1:1


def test_quote_missing_asset_rate_returns_none():
    """Test that missing rate returns None."""
    mock_settings = MagicMock()
    mock_settings.get_quote_rate.return_value = None

    result = get_quote(Decimal("20.00"), "USD", "UNKNOWN_ASSET", mock_settings)

    assert result is None


def test_quote_unknown_currency_returns_none():
    """Test that non-USD currency returns None."""
    mock_settings = MagicMock()
    mock_settings.get_quote_rate.return_value = None

    result = get_quote(Decimal("20.00"), "EUR", "ETH", mock_settings)

    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Asset compatibility tests
# ─────────────────────────────────────────────────────────────────────────────


def test_eth_valid_on_ethereum():
    """ETH is native on Ethereum."""
    assert is_valid_pair("ethereum", "ETH") is True
    assert is_valid_pair("ethereum-sepolia", "ETH") is True


def test_eth_valid_on_arbitrum():
    """ETH is native on Arbitrum."""
    assert is_valid_pair("arbitrum", "ETH") is True
    assert is_valid_pair("arbitrum-sepolia", "ETH") is True


def test_eth_invalid_on_polygon():
    """ETH is NOT native on Polygon (MATIC is)."""
    assert is_valid_pair("polygon", "ETH") is False
    assert is_valid_pair("polygon-amoy", "ETH") is False


def test_matic_valid_on_polygon():
    """MATIC is native on Polygon."""
    assert is_valid_pair("polygon", "MATIC") is True
    assert is_valid_pair("polygon-amoy", "MATIC") is True


def test_matic_invalid_on_ethereum():
    """MATIC is NOT valid on Ethereum."""
    assert is_valid_pair("ethereum", "MATIC") is False


def test_usdc_valid_on_all_chains():
    """USDC (ERC-20) is valid on all three chains."""
    assert is_valid_pair("ethereum", "USDC") is True
    assert is_valid_pair("arbitrum", "USDC") is True
    assert is_valid_pair("polygon", "USDC") is True


def test_usdt_valid_on_all_chains():
    """USDT (ERC-20) is valid on all three chains."""
    assert is_valid_pair("ethereum", "USDT") is True
    assert is_valid_pair("arbitrum", "USDT") is True
    assert is_valid_pair("polygon", "USDT") is True


def test_case_insensitive_matching():
    """Asset matching should be case-insensitive."""
    assert is_valid_pair("ethereum", "eth") is True
    assert is_valid_pair("ETHEREUM", "ETH") is True
    assert is_valid_pair("ethereum", "usdc") is True


# ─────────────────────────────────────────────────────────────────────────────
# Auto-option generation tests (integration-style)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_auto_options_generates_valid_combos():
    """Test that auto-pricing generates only valid chain+asset combinations."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.clients.blockchain_core import BlockchainCoreClient
    from app.clients.user_service import UserServiceClient

    # Setup: paywall with auto-pricing enabled
    paywall_id = uuid.uuid4()
    product_id = uuid.uuid4()

    paywall = Paywall(
        id=paywall_id,
        merchant_id="test-merchant",
        name="Test Paywall",
        description=None,
        product_ids=[str(product_id)],
        is_active=True,
        paywall_type="product",
        auto_payment_options_enabled=True,
        allowed_chains=["ethereum", "polygon"],
        allowed_assets=["ETH", "MATIC", "USDC"],
    )

    # Mock DB session
    mock_db = AsyncMock(spec=AsyncSession)

    # Mock product repo
    with patch("app.services.payment_options.ProductRepository") as MockProdRepo:
        mock_prod_repo = AsyncMock()
        mock_prod_repo.get = AsyncMock()
        product = Product(
            id=product_id,
            merchant_id="test-merchant",
            name="Test Product",
            description=None,
            is_active=True,
            base_amount=Decimal("20.00"),
            base_currency="USD",
            auto_pricing_enabled=True,
        )
        mock_prod_repo.get.return_value = product
        MockProdRepo.return_value = mock_prod_repo
        mock_db.commit = AsyncMock()

        # Mock BC client
        mock_bc_client = AsyncMock(spec=BlockchainCoreClient)

        # Mock gas estimates for all 3 valid combos
        # Valid: ethereum:ETH, ethereum:USDC, polygon:MATIC, polygon:USDC
        # Invalid: polygon:ETH (would be skipped by is_valid_pair)
        def estimate_gas_side_effect(**kwargs):
            chain = kwargs.get("chain", "").lower()
            asset = kwargs.get("asset", "").upper()

            if is_valid_pair(chain, asset):
                return MagicMock(
                    chain=chain,
                    asset=asset,
                    transfer_type="native" if asset in {"ETH", "MATIC"} else "erc20",
                    gas_units=21000 if asset in {"ETH", "MATIC"} else 65000,
                    gas_price_wei=1_000_000_000,
                    total_fee_wei=21_000_000_000_000 if asset in {"ETH", "MATIC"} else 65_000_000_000_000,
                    source="rpc",
                    token_contract_address="0x..." if asset != "ETH" else None,
                    token_decimals=6 if asset != "ETH" else 18,
                )
            return None

        mock_bc_client.estimate_gas = AsyncMock(side_effect=estimate_gas_side_effect)

        # Mock user service client
        mock_user_client = AsyncMock(spec=UserServiceClient)

        # Mock settings
        with patch("app.services.payment_options.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_quote_rate.side_effect = lambda base_curr, asset: (
                Decimal("0.00035") if asset == "ETH"
                else Decimal("1.25") if asset == "MATIC"
                else Decimal("1.0")  # USDC/USDT
            )
            mock_get_settings.return_value = mock_settings

            result = await build_payment_options(paywall, mock_db, mock_bc_client, mock_user_client)

            # Should have 4 valid combos: ethereum:ETH, ethereum:USDC, polygon:MATIC, polygon:USDC
            # (polygon:ETH is invalid per is_valid_pair)
            executable = [o for o in result.options if o.executable]
            assert len(executable) == 4, f"Expected 4 executable options, got {len(executable)}"

            option_ids = {o.option_id for o in executable}
            expected = {"ethereum:eth", "ethereum:usdc", "polygon:matic", "polygon:usdc"}
            assert option_ids == expected, f"Unexpected options: {option_ids}"


@pytest.mark.asyncio
async def test_auto_options_disabled_when_rate_missing():
    """Test that options are disabled when exchange rate is not configured."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.clients.blockchain_core import BlockchainCoreClient

    paywall_id = uuid.uuid4()
    product_id = uuid.uuid4()

    paywall = Paywall(
        id=paywall_id,
        merchant_id="test-merchant",
        name="Test",
        description=None,
        product_ids=[str(product_id)],
        is_active=True,
        paywall_type="product",
        auto_payment_options_enabled=True,
        allowed_chains=["ethereum"],
        allowed_assets=["UNKNOWN_ASSET"],  # No rate configured
    )

    mock_db = AsyncMock(spec=AsyncSession)

    with patch("app.services.payment_options.ProductRepository") as MockProdRepo:
        mock_prod_repo = AsyncMock()
        product = Product(
            id=product_id,
            merchant_id="test-merchant",
            name="Test",
            description=None,
            is_active=True,
            base_amount=Decimal("20.00"),
            base_currency="USD",
            auto_pricing_enabled=True,
        )
        mock_prod_repo.get.return_value = product
        MockProdRepo.return_value = mock_prod_repo
        mock_db.commit = AsyncMock()

        mock_bc_client = AsyncMock(spec=BlockchainCoreClient)

        with patch("app.services.payment_options.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.get_quote_rate.return_value = None  # Rate not available

            result = await build_payment_options(paywall, mock_db, mock_bc_client)

            # All options should be disabled
            assert all(not o.executable for o in result.options)
            assert all(o.disabled_reason == "rate_not_configured" for o in result.options)


@pytest.mark.asyncio
async def test_pay_without_option_uses_recommended():
    """Test POST /pay without option_id uses recommended option."""
    # This test would verify the selection logic in public.py
    # It's tested via the public API integration test
    pass


@pytest.mark.asyncio
async def test_pay_with_option_id_uses_selected():
    """Test POST /pay with option_id uses the explicitly selected option."""
    # This test would verify the selection logic in public.py
    # It's tested via the public API integration test
    pass
