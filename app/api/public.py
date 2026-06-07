"""Public (unauthenticated) endpoints — customer-facing checkout flow."""

import json
import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.blockchain_core import BlockchainCoreClient, get_blockchain_core_client
from app.clients.user_service import UserServiceClient, get_user_service_client
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.repositories.checkout_session import CheckoutSessionRepository
from app.repositories.paywall import PaywallRepository
from app.repositories.payment_intent import PaymentEventRepository, PaymentIntentRepository
from app.repositories.product import ProductPriceRepository
from app.schemas.payment_options import PaymentOptionsResponse
from app.schemas.paywall import PAYWALL_TYPE_PRODUCT, PaywallResponse
from app.services.paywall import PaywallService
from app.services.payment_options import build_payment_options
from app.services.price_oracle import get_price

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/public", tags=["public"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PublicPayRequest(BaseModel):
    """Customer selects a payment option (or takes the recommended one)."""
    option_id: str | None = None          # select by option ID (preferred method)
    product_price_id: str | None = None   # select by price UUID (backward compat)
    chain: str | None = None              # select by chain+asset (backward compat)
    asset: str | None = None
    payer_address: str | None = None


class PublicPayResponse(BaseModel):
    payment_intent_id: str
    amount: str
    asset: str
    chain: str
    transfer_type: str
    token_contract_address: str | None
    token_decimals: int
    status: str
    recipient_address: str | None
    estimated_fee_wei: str | None
    estimated_fee_native: str | None
    selected_option_id: str | None
    was_recommended_selected: bool
    estimated_confirmation_readable: str | None = None  # ETA display


class PublicIntentStatusResponse(BaseModel):
    payment_intent_id: str
    status: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/paywalls/{paywall_id}", response_model=PaywallResponse)
async def public_get_paywall(
    paywall_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PaywallResponse:
    """Return active paywall info — no merchant auth required."""
    repo = PaywallRepository(db)
    paywall = await repo.get(paywall_id)
    if paywall is None or not paywall.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paywall not found")
    service = PaywallService(db)
    return await service._to_response(paywall)


@router.get(
    "/paywalls/{paywall_id}/payment-options",
    response_model=PaymentOptionsResponse,
)
async def public_get_payment_options(
    paywall_id: UUID,
    db: AsyncSession = Depends(get_db),
    blockchain_client: BlockchainCoreClient = Depends(get_blockchain_core_client),
    user_service_client: UserServiceClient = Depends(get_user_service_client),
) -> PaymentOptionsResponse:
    """Return all available payment options with fee estimates.

    Each option represents a chain+asset combination available for this paywall.
    Options are sorted by estimated network fee (cheapest first) and the
    cheapest executable option is marked as recommended.
    """
    repo = PaywallRepository(db)
    paywall = await repo.get(paywall_id)
    if paywall is None or not paywall.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paywall not found")
    return await build_payment_options(paywall, db, blockchain_client, user_service_client)


@router.post(
    "/paywalls/{paywall_id}/pay",
    response_model=PublicPayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def public_pay(
    paywall_id: UUID,
    body: PublicPayRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    blockchain_client: BlockchainCoreClient = Depends(get_blockchain_core_client),
    user_service_client: UserServiceClient = Depends(get_user_service_client),
) -> PublicPayResponse:
    """Create a PaymentIntent for the selected payment option.

    Selection priority:
    1. option_id        — use this exact option (preferred for auto/manual)
    2. product_price_id — use this exact price (backward compat)
    3. chain + asset    — find matching option (backward compat)
    4. no selection     — use recommended (cheapest executable) option

    Returns the intent with deposit address and fee estimate.
    """
    paywall_repo = PaywallRepository(db)
    paywall = await paywall_repo.get(paywall_id)
    if paywall is None or not paywall.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paywall not found")

    # --- Resolve payment option -------------------------------------------
    options_resp = await build_payment_options(paywall, db, blockchain_client, user_service_client)
    executable = [o for o in options_resp.options if o.executable]

    if not executable:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No executable payment options available for this paywall.",
        )

    selected = None
    was_recommended = False

    # Selection by option_id (preferred)
    if body.option_id:
        selected = next(
            (o for o in executable if o.option_id == body.option_id), None
        )
        if selected is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Option ID {body.option_id} is not an executable option for this paywall.",
            )

    # Selection by product_price_id (backward compat)
    elif body.product_price_id:
        selected = next(
            (o for o in executable if o.product_price_id == body.product_price_id), None
        )
        if selected is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Price ID {body.product_price_id} is not an executable option for this paywall.",
            )

    # Selection by chain + asset (backward compat)
    elif body.chain and body.asset:
        opt_id = f"{body.chain.lower()}:{body.asset.upper()}"
        selected = next((o for o in executable if o.option_id == opt_id), None)
        if selected is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No executable option found for chain={body.chain} asset={body.asset}.",
            )

    # Default: recommended
    else:
        selected = next((o for o in executable if o.recommended), None) or executable[0]
        was_recommended = selected.recommended

    if selected.recommended and not was_recommended:
        was_recommended = True

    # --- Get price details --------------------------------------------------
    asset = selected.asset.upper()
    chain = selected.chain.lower()

    if selected.product_price_id:
        # Manual ProductPrice — fetch from DB
        price_repo = ProductPriceRepository(db)
        price = await price_repo.get(UUID(selected.product_price_id))
        if not price:
            raise HTTPException(status_code=400, detail="Selected price not found.")
        amount = Decimal(str(price.amount))
    else:
        # Auto-priced or quick paywall — amount already quoted in option
        amount = Decimal(selected.amount)

    # --- Create PaymentIntent -----------------------------------------------
    intent_repo = PaymentIntentRepository(db)
    event_repo = PaymentEventRepository(db)

    product_price_id_uuid = UUID(selected.product_price_id) if selected.product_price_id else None

    intent = await intent_repo.create(
        merchant_id=paywall.merchant_id,
        asset=asset,
        chain=chain,
        amount=amount,
        product_price_id=product_price_id_uuid,
        payer_address=body.payer_address or None,
        recipient_address=None,
    )

    # Fetch and lock the current price (protects merchant from volatility)
    try:
        rate_at_creation = await get_price(asset)
        intent.rate_at_creation = rate_at_creation
        logger.info(
            "Locked price for payment intent %s: %s=$%s",
            intent.id,
            asset,
            rate_at_creation,
        )
    except Exception as exc:
        logger.error("Failed to fetch price for %s: %s", asset, exc)
        intent.rate_at_creation = None

    # Derive unique deposit address from Blockchain Core
    unique_address = await blockchain_client.get_deposit_address(str(intent.id))
    recipient_address = unique_address or settings.get_aggregator_wallet(chain)

    intent.recipient_address = recipient_address

    await db.flush()
    await event_repo.create(
        payment_intent_id=intent.id,
        event_type="created",
        to_status="pending",
    )

    return PublicPayResponse(
        payment_intent_id=str(intent.id),
        amount=str(intent.amount),
        asset=intent.asset,
        chain=intent.chain,
        transfer_type=selected.transfer_type,
        token_contract_address=selected.token_contract_address,
        token_decimals=selected.token_decimals,
        status=intent.status,
        recipient_address=recipient_address,
        estimated_fee_wei=selected.estimated_fee_wei,
        estimated_fee_native=selected.estimated_fee_native,
        selected_option_id=selected.option_id,
        was_recommended_selected=was_recommended,
        estimated_confirmation_readable=None,
    )


# ---------------------------------------------------------------------------
# /public/checkout-sessions/* → Checkout session endpoints
# ---------------------------------------------------------------------------


class PublicCheckoutSessionResponse(BaseModel):
    """Checkout session details for customer-facing checkout."""
    session_id: str
    amount: str
    currency: str
    asset: str | None
    chain: str | None
    expires_at: str


class PublicSessionPayRequest(BaseModel):
    """Customer initiates payment from checkout session."""
    session_id: str | None = None  # For clarity
    option_id: str | None = None   # select by option ID
    chain: str | None = None       # override chain
    asset: str | None = None       # override asset
    payer_address: str | None = None


@router.get(
    "/checkout-sessions/{session_id}",
    response_model=PublicCheckoutSessionResponse,
)
async def public_get_checkout_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PublicCheckoutSessionResponse:
    """Get checkout session details — used by frontend to render session checkout page."""
    repo = CheckoutSessionRepository(db)
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkout session not found",
        )
    return PublicCheckoutSessionResponse(
        session_id=str(session.id),
        amount=str(session.amount),
        currency=session.currency,
        asset=session.asset,
        chain=session.chain,
        expires_at=session.expires_at.isoformat(),
    )


@router.get(
    "/checkout-sessions/{session_id}/payment-options",
    response_model=PaymentOptionsResponse,
)
async def public_get_session_payment_options(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    blockchain_client: BlockchainCoreClient = Depends(get_blockchain_core_client),
    user_service_client: UserServiceClient = Depends(get_user_service_client),
) -> PaymentOptionsResponse:
    """Get payment options for a checkout session.

    Generates payment options based on session's currency and optional asset/chain.
    """
    repo = CheckoutSessionRepository(db)
    session = await repo.get(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkout session not found",
        )

    # Create a temporary paywall-like object for the payment options builder
    # The session amount is in base currency, so we build options from it
    # This leverages existing payment option generation logic

    # For now, we'll return a simplified response that the frontend can use
    # In production, you'd integrate with the quote service to get crypto amounts

    options_resp = PaymentOptionsResponse(
        options=[],
        pricing_mode="auto",
        base_amount=str(session.amount),
        base_currency=session.currency,
        recommended_option_id=None,
    )

    # If session has pre-selected asset/chain, build a single option
    if session.asset and session.chain:
        # This would call the quote service to convert currency to crypto
        # For MVP, we'll return a basic option structure
        options_resp.options = [{
            "option_id": f"{session.chain.lower()}:{session.asset.upper()}",
            "product_price_id": None,
            "chain": session.chain.lower(),
            "chain_display_name": session.chain.capitalize(),
            "asset": session.asset.upper(),
            "amount": str(session.amount),  # Placeholder - should be converted
            "transfer_type": "erc20" if session.asset != "ETH" else "native",
            "token_contract_address": None,
            "token_decimals": 18,
            "executable": True,
            "recommended": True,
            "estimated_fee_wei": None,
            "estimated_fee_native": None,
            "source": "static",
        }]
        options_resp.recommended_option_id = options_resp.options[0]["option_id"]

    return options_resp


@router.post(
    "/checkout-sessions/{session_id}/pay",
    response_model=PublicPayResponse,
    status_code=status.HTTP_201_CREATED,
)
async def public_pay_session(
    session_id: UUID,
    body: PublicSessionPayRequest,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    blockchain_client: BlockchainCoreClient = Depends(get_blockchain_core_client),
    user_service_client: UserServiceClient = Depends(get_user_service_client),
) -> PublicPayResponse:
    """Create a PaymentIntent from a checkout session."""
    session_repo = CheckoutSessionRepository(db)
    session = await session_repo.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkout session not found",
        )

    # Validate session not expired
    from datetime import datetime
    if session.expires_at < datetime.now(session.expires_at.tzinfo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Checkout session has expired",
        )

    # Determine asset and chain for this payment
    asset = body.asset or session.asset
    chain = body.chain or session.chain

    if not asset or not chain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset and chain must be specified (in session or request)",
        )

    # Get merchant from session (stored implicitly in paywall context)
    # For session-based checkout, we need to fetch the merchant via User Service lookup
    # This is a limitation of the current design - sessions don't store merchant_id directly
    # For MVP, we'll use a placeholder merchant_id
    merchant_id = session.merchant_id

    # Create PaymentIntent
    intent_repo = PaymentIntentRepository(db)
    event_repo = PaymentEventRepository(db)

    intent = await intent_repo.create(
        merchant_id=merchant_id,
        asset=asset.upper(),
        chain=chain.lower(),
        amount=session.amount,
        product_price_id=None,
        payer_address=body.payer_address or None,
        recipient_address=None,
    )

    # Fetch and lock the current price (protects merchant from volatility)
    try:
        rate_at_creation = await get_price(asset.upper())
        intent.rate_at_creation = rate_at_creation
        logger.info(
            "Locked price for payment intent %s: %s=$%s",
            intent.id,
            asset.upper(),
            rate_at_creation,
        )
    except Exception as exc:
        logger.error("Failed to fetch price for %s: %s", asset.upper(), exc)
        intent.rate_at_creation = None

    # Derive unique deposit address
    unique_address = await blockchain_client.get_deposit_address(str(intent.id))
    recipient_address = unique_address or settings.get_aggregator_wallet(chain)

    intent.recipient_address = recipient_address

    # Store session_id in intent metadata
    metadata = {"session_id": str(session_id)}
    if session.metadata_json:
        metadata.update(json.loads(session.metadata_json))
    intent.metadata_json = json.dumps(metadata)

    await db.flush()
    await event_repo.create(
        payment_intent_id=intent.id,
        event_type="created",
        to_status="pending",
    )

    # Mark session as used
    await session_repo.mark_used(session_id, intent.id)

    await db.commit()

    # Determine transfer type based on asset
    # POL is Polygon's native token (upgraded from MATIC on Sep 4, 2024)
    transfer_type = "native" if asset.upper() in ["ETH", "POL"] else "erc20"

    return PublicPayResponse(
        payment_intent_id=str(intent.id),
        amount=str(intent.amount),
        asset=intent.asset,
        chain=intent.chain,
        transfer_type=transfer_type,
        token_contract_address=None,  # Would need contract lookup for ERC-20
        token_decimals=18,
        status=intent.status,
        recipient_address=recipient_address,
        estimated_fee_wei=None,
        estimated_fee_native=None,
        selected_option_id=f"{chain.lower()}:{asset.upper()}",
        was_recommended_selected=True,
        estimated_confirmation_readable=None,
    )


@router.get(
    "/payment-intents/{payment_intent_id}/status",
    response_model=PublicIntentStatusResponse,
)
async def public_get_intent_status(
    payment_intent_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> PublicIntentStatusResponse:
    """Poll payment intent status — used by checkout page while awaiting confirmation."""
    repo = PaymentIntentRepository(db)
    intent = await repo.get(payment_intent_id)
    if intent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment intent not found")
    return PublicIntentStatusResponse(
        payment_intent_id=str(intent.id),
        status=intent.status,
    )
