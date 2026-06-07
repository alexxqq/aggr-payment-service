"""Payment options service.

Builds the list of available payment options for a checkout.

Supports two modes:
1. Manual: CustomerPrice records explicitly created by merchant
2. Auto: Generated on-the-fly from product base price + merchant allowed chains/assets
"""

import asyncio
import logging
import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.blockchain_core import BlockchainCoreClient
from app.clients.user_service import UserServiceClient
from app.core.config import Settings, get_settings
from app.models.paywall import Paywall, PAYWALL_TYPE_PRODUCT, PAYWALL_TYPE_QUICK
from app.repositories.product import ProductRepository, ProductPriceRepository
from app.schemas.payment_options import PaymentOptionItem, PaymentOptionsResponse
from app.services.asset_compat import is_valid_pair
from app.services.quote import get_quote
from app.services.price_oracle import get_price

logger = logging.getLogger(__name__)

_CHAIN_DISPLAY_NAMES: dict[str, str] = {
    "ethereum": "Ethereum",
    "arbitrum": "Arbitrum",
    "polygon": "Polygon",
    "ethereum-sepolia": "Ethereum Sepolia",
    "arbitrum-sepolia": "Arbitrum Sepolia",
    "polygon-amoy": "Polygon Amoy",
}

_NATIVE_ASSETS = {"ETH", "POL"}  # POL is Polygon's native token since Sep 4, 2024


def _transfer_type(asset: str) -> str:
    return "native" if asset.upper() in _NATIVE_ASSETS else "erc20"


def _option_id(chain: str, asset: str) -> str:
    return f"{chain.lower()}:{asset.upper()}"


def _fee_native_str(fee_wei: int) -> str:
    """Convert wei to human-readable ETH string."""
    return f"{fee_wei / 1e18:.9f}".rstrip("0").rstrip(".")


def _fee_usd_str(fee_wei: int, native_token_price_usd: Decimal) -> str | None:
    """Convert wei to USD using chain-specific native token price.

    Args:
        fee_wei: fee amount in wei
        native_token_price_usd: price of 1 unit of native token in USD (e.g., 1560 for ETH at $1560)

    Returns:
        Formatted USD string (without $), or None if price is missing.
    """
    if native_token_price_usd is None or native_token_price_usd <= 0:
        return None
    fee_native_units = Decimal(fee_wei) / Decimal(1e18)
    fee_usd = fee_native_units * native_token_price_usd  # multiply by price
    # Show more precision for small fees (< $0.01), otherwise standard 2 decimals
    if fee_usd < Decimal("0.01"):
        return f"{fee_usd:.4f}"
    else:
        return f"{fee_usd:.2f}"


async def _estimate_fee(
    bc_client: BlockchainCoreClient,
    chain: str,
    asset: str,
    transfer_type: str,
) -> dict | None:
    """Call Blockchain Core gas estimate. Returns dict or None on failure."""
    try:
        return await bc_client.estimate_gas(
            chain=chain,
            asset=asset,
            transfer_type=transfer_type,
        )
    except Exception as exc:
        logger.warning("Gas estimate failed for %s/%s: %s", chain, asset, exc)
        return None


def _is_auto_mode(paywall: Paywall) -> bool:
    """Check if paywall is in auto-pricing mode."""
    return bool(paywall.auto_payment_options_enabled)


async def _resolve_allowed(
    paywall: Paywall,
    user_service_client: UserServiceClient | None,
) -> tuple[list[str], list[str]]:
    """Resolve allowed chains and assets for this paywall.

    Priority:
    1. Paywall-level allowed_chains/assets (if set)
    2. Merchant capabilities from User Service
    3. Empty lists (no options generated)
    """
    chains = paywall.allowed_chains or []
    assets = paywall.allowed_assets or []

    if (not chains or not assets) and user_service_client:
        try:
            caps = await user_service_client.get_merchant_capabilities(paywall.merchant_id)
            if not chains:
                chains = caps.allowed_chains or []
            if not assets:
                assets = caps.allowed_assets or []
        except Exception as exc:
            logger.warning("Failed to fetch merchant capabilities: %s", exc)

    return chains, assets


async def _build_manual_options(
    paywall: Paywall,
    db: AsyncSession,
    bc_client: BlockchainCoreClient,
) -> PaymentOptionsResponse:
    """Build payment options from explicitly created ProductPrice records.

    This is the original behavior — merchant manually creates prices for each chain+asset.
    """
    price_repo = ProductPriceRepository(db)
    product_name: str | None = None

    # Collect candidate prices
    candidates: list[tuple] = []

    if paywall.paywall_type == PAYWALL_TYPE_QUICK:
        if paywall.asset and paywall.chain and paywall.amount:
            candidates.append((None, paywall.chain, paywall.asset, paywall.amount, None))

    elif paywall.paywall_type == PAYWALL_TYPE_PRODUCT:
        if paywall.product_price_id:
            price = await price_repo.get(paywall.product_price_id)
            if price and price.is_active:
                candidates.append((str(price.id), price.chain, price.asset, price.amount, None))

        # Additional prices from product_ids array
        if paywall.product_ids:
            prod_repo = ProductRepository(db)
            for pid_str in paywall.product_ids:
                try:
                    pid = uuid.UUID(str(pid_str))
                except ValueError:
                    continue
                product = await prod_repo.get(pid)
                if not product or not product.is_active:
                    continue
                if product_name is None:
                    product_name = product.name
                prices = await price_repo.list_by_product(pid)
                for price in prices:
                    if not price.is_active:
                        continue
                    if str(price.id) not in [c[0] for c in candidates if c[0]]:
                        candidates.append(
                            (str(price.id), price.chain, price.asset, price.amount, product.name)
                        )
                        if product_name is None:
                            product_name = product.name

    # Estimate fees in parallel
    async def _build_option(price_id, chain, asset, amount, prod_name) -> PaymentOptionItem:
        asset_upper = asset.upper()
        chain_lower = chain.lower()
        tt = _transfer_type(asset_upper)
        oid = _option_id(chain_lower, asset_upper)

        est = await _estimate_fee(bc_client, chain_lower, asset_upper, tt)

        if est is None:
            return PaymentOptionItem(
                option_id=oid,
                product_price_id=price_id,
                chain=chain_lower,
                chain_display_name=_CHAIN_DISPLAY_NAMES.get(chain_lower, chain_lower.title()),
                asset=asset_upper,
                amount=str(amount),
                transfer_type=tt,
                token_contract_address=None,
                token_decimals=6 if tt == "erc20" else 18,
                estimated_fee_wei=None,
                estimated_fee_native=None,
                source="error",
                recommended=False,
                executable=False,
                reason=None,
                disabled_reason="gas_estimation_failed",
                pricing_mode="manual",
            )

        executable = True
        disabled_reason: str | None = None
        source = est.get("source", "fallback")

        if tt == "erc20" and not est.get("token_contract_address"):
            executable = False
            disabled_reason = "token_contract_not_configured"
            source = "disabled"

        fee_wei = est.get("total_fee_wei", 0)

        return PaymentOptionItem(
            option_id=oid,
            product_price_id=price_id,
            chain=chain_lower,
            chain_display_name=_CHAIN_DISPLAY_NAMES.get(chain_lower, chain_lower.title()),
            asset=asset_upper,
            amount=str(amount),
            transfer_type=tt,
            token_contract_address=est.get("token_contract_address"),
            token_decimals=est.get("token_decimals", 18),
            estimated_fee_wei=str(fee_wei) if fee_wei else None,
            estimated_fee_native=_fee_native_str(fee_wei) if fee_wei else None,
            source=source,
            recommended=False,
            executable=executable,
            reason=None,
            disabled_reason=disabled_reason,
            pricing_mode="manual",
        )

    tasks = [_build_option(*c) for c in candidates]
    options: list[PaymentOptionItem] = await asyncio.gather(*tasks)

    # Sort and recommend
    executable_options = [o for o in options if o.executable and o.estimated_fee_wei]

    def _sort_key(o: PaymentOptionItem) -> int:
        try:
            return int(o.estimated_fee_wei)
        except Exception:
            return 10 ** 18

    executable_options.sort(key=_sort_key)

    recommended_id: str | None = None
    if executable_options:
        cheapest = executable_options[0]
        cheapest.recommended = True
        recommended_id = cheapest.option_id
        if len(executable_options) == 1:
            cheapest.reason = "single_available_option"
        else:
            cheapest.reason = "lowest_estimated_fee"

    disabled_options = [o for o in options if not o.executable]
    final_options = executable_options + disabled_options

    return PaymentOptionsResponse(
        paywall_id=str(paywall.id),
        product_name=product_name,
        cost_optimization_enabled=True,
        recommended_option_id=recommended_id,
        options=final_options,
        pricing_mode="manual",
    )


async def _build_auto_options(
    paywall: Paywall,
    db: AsyncSession,
    bc_client: BlockchainCoreClient,
    user_service_client: UserServiceClient | None,
) -> PaymentOptionsResponse:
    """Build payment options from product base price + allowed chains/assets.

    Auto-generates all valid chain+asset combinations, quotes the base amount,
    estimates gas, and recommends the cheapest.
    """
    settings = get_settings()
    prod_repo = ProductRepository(db)

    # Load the first product with auto_pricing_enabled
    product = None
    if paywall.product_ids:
        for pid_str in paywall.product_ids:
            try:
                pid = uuid.UUID(str(pid_str))
            except ValueError:
                continue
            p = await prod_repo.get(pid)
            if p and p.is_active and p.auto_pricing_enabled and p.base_amount:
                product = p
                break

    if not product:
        logger.warning("Auto-pricing enabled but no valid product found")
        return PaymentOptionsResponse(
            paywall_id=str(paywall.id),
            product_name=None,
            cost_optimization_enabled=True,
            recommended_option_id=None,
            options=[],
            pricing_mode="auto",
        )

    # Resolve allowed chains and assets
    allowed_chains, allowed_assets = await _resolve_allowed(paywall, user_service_client)

    if not allowed_chains or not allowed_assets:
        logger.warning("No allowed chains/assets for auto-pricing paywall %s", paywall.id)
        return PaymentOptionsResponse(
            paywall_id=str(paywall.id),
            product_name=product.name,
            cost_optimization_enabled=True,
            recommended_option_id=None,
            options=[],
            pricing_mode="auto",
            base_amount=str(product.base_amount),
            base_currency=product.base_currency,
        )

    # Build all valid (chain, asset) combinations
    candidates: list[tuple[str, str]] = []
    for chain in allowed_chains:
        for asset in allowed_assets:
            if is_valid_pair(chain, asset):
                candidates.append((chain, asset))

    # Estimate fees in parallel
    async def _build_auto_option(chain: str, asset: str) -> PaymentOptionItem:
        asset_upper = asset.upper()
        chain_lower = chain.lower()
        tt = _transfer_type(asset_upper)
        oid = _option_id(chain_lower, asset_upper)

        # Quote the base amount to crypto using live PriceOracle
        quote_result = await get_quote(
            product.base_amount,
            product.base_currency or "USD",
            asset_upper,
        )

        if quote_result is None:
            return PaymentOptionItem(
                option_id=oid,
                product_price_id=None,
                chain=chain_lower,
                chain_display_name=_CHAIN_DISPLAY_NAMES.get(chain_lower, chain_lower.title()),
                asset=asset_upper,
                amount="0",  # placeholder
                transfer_type=tt,
                token_contract_address=None,
                token_decimals=6 if tt == "erc20" else 18,
                estimated_fee_wei=None,
                estimated_fee_native=None,
                source="disabled",
                recommended=False,
                executable=False,
                reason=None,
                disabled_reason="rate_not_configured",
                pricing_mode="auto",
            )

        # Estimate gas
        est = await _estimate_fee(bc_client, chain_lower, asset_upper, tt)

        if est is None:
            return PaymentOptionItem(
                option_id=oid,
                product_price_id=None,
                chain=chain_lower,
                chain_display_name=_CHAIN_DISPLAY_NAMES.get(chain_lower, chain_lower.title()),
                asset=asset_upper,
                amount=str(quote_result.crypto_amount),
                transfer_type=tt,
                token_contract_address=None,
                token_decimals=6 if tt == "erc20" else 18,
                estimated_fee_wei=None,
                estimated_fee_native=None,
                source="error",
                recommended=False,
                executable=False,
                reason=None,
                disabled_reason="gas_estimation_failed",
                pricing_mode="auto",
            )

        # Check if token contract is configured for ERC-20
        executable = True
        disabled_reason: str | None = None
        source = est.get("source", "fallback")

        if tt == "erc20" and not est.get("token_contract_address"):
            executable = False
            disabled_reason = "token_contract_not_configured"
            source = "disabled"

        fee_wei = est.get("total_fee_wei", 0)
        # Fetch live price from PriceOracle for accurate fee display
        # Polygon uses POL (upgraded from MATIC on Sep 4, 2024)
        native_token = "POL" if chain_lower == "polygon" else "ETH"
        try:
            native_token_price = await get_price(native_token)
        except Exception as exc:
            logger.warning("Failed to fetch price for %s: %s, using fallback", native_token, exc)
            native_token_price = None
        fee_usd = _fee_usd_str(fee_wei, native_token_price) if executable else None

        # Total cost = base amount + fee
        base_usd = str(product.base_amount) if product.base_currency == "USD" else "0"
        total_usd = None
        if fee_usd and executable:
            try:
                total_usd = f"{Decimal(base_usd) + Decimal(fee_usd):.2f}"
            except Exception:
                total_usd = None

        return PaymentOptionItem(
            option_id=oid,
            product_price_id=None,
            chain=chain_lower,
            chain_display_name=_CHAIN_DISPLAY_NAMES.get(chain_lower, chain_lower.title()),
            asset=asset_upper,
            amount=str(quote_result.crypto_amount),
            transfer_type=tt,
            token_contract_address=est.get("token_contract_address"),
            token_decimals=est.get("token_decimals", 18),
            estimated_fee_wei=str(fee_wei) if fee_wei else None,
            estimated_fee_native=_fee_native_str(fee_wei) if fee_wei else None,
            source=source,
            recommended=False,
            executable=executable,
            reason=None,
            disabled_reason=disabled_reason,
            pricing_mode="auto",
            estimated_fee_usd=fee_usd,
            total_estimated_cost_usd=total_usd,
        )

    tasks = [_build_auto_option(chain, asset) for chain, asset in candidates]
    options: list[PaymentOptionItem] = await asyncio.gather(*tasks)

    # Sort and recommend by total cost (or fee if total not available)
    executable_options = [o for o in options if o.executable and o.estimated_fee_wei]

    def _sort_key(o: PaymentOptionItem) -> tuple:
        try:
            # Sort by total cost first (if available), then by fee as tiebreaker
            if o.total_estimated_cost_usd:
                return (0, float(o.total_estimated_cost_usd))
            else:
                return (1, int(o.estimated_fee_wei))
        except Exception:
            return (2, 10 ** 18)

    executable_options.sort(key=_sort_key)

    recommended_id: str | None = None
    if executable_options:
        cheapest = executable_options[0]
        cheapest.recommended = True
        recommended_id = cheapest.option_id
        if len(executable_options) == 1:
            cheapest.reason = "single_available_option"
        else:
            cheapest.reason = "lowest_total_estimated_cost"

    disabled_options = [o for o in options if not o.executable]
    final_options = executable_options + disabled_options

    return PaymentOptionsResponse(
        paywall_id=str(paywall.id),
        product_name=product.name,
        cost_optimization_enabled=True,
        recommended_option_id=recommended_id,
        options=final_options,
        pricing_mode="auto",
        base_amount=str(product.base_amount),
        base_currency=product.base_currency,
    )


async def build_payment_options(
    paywall: Paywall,
    db: AsyncSession,
    bc_client: BlockchainCoreClient,
    user_service_client: UserServiceClient | None = None,
) -> PaymentOptionsResponse:
    """Build the full payment options list for a paywall.

    Supports two modes:
    1. Manual: Uses explicitly created ProductPrice records
    2. Auto: Generates options from product base price + merchant allowed chains/assets

    Args:
        paywall: The paywall to build options for
        db: Database session
        bc_client: Blockchain Core client for gas estimation
        user_service_client: Optional User Service client for merchant capabilities

    Returns:
        PaymentOptionsResponse with sorted, recommended options.
    """
    if _is_auto_mode(paywall):
        return await _build_auto_options(paywall, db, bc_client, user_service_client)
    else:
        return await _build_manual_options(paywall, db, bc_client)
