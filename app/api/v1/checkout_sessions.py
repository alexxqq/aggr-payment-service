"""Merchant-facing checkout session API — low-code integration for e-commerce."""

import json
import logging
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.user_service import UserServiceClient, get_user_service_client
from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.repositories.checkout_session import CheckoutSessionRepository
from app.schemas.checkout_session import (
    CheckoutSessionResponse,
    CreateCheckoutSessionRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/checkout-sessions", tags=["checkout-sessions"])


def _merchant_id(x_merchant_id: str = Header(...)) -> str:
    """Extract merchant identity from gateway-injected header."""
    return x_merchant_id


@router.post(
    "",
    response_model=CheckoutSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dynamic checkout session",
    description=(
        "Merchant creates a checkout session for a specific amount and currency. "
        "Returns a unique checkout URL that can be shared with customers. "
        "The session expires after the specified duration."
    ),
)
async def create_checkout_session(
    body: CreateCheckoutSessionRequest,
    merchant_id: str = Depends(_merchant_id),
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user_service: UserServiceClient = Depends(get_user_service_client),
) -> CheckoutSessionResponse:
    """Create a checkout session with a fixed amount for low-code integration.

    Merchant provides:
    - amount: payment amount in base currency (USD, EUR, etc)
    - currency: ISO currency code
    - (optional) asset & chain: pre-select crypto option
    - (optional) redirect URLs: post-payment flow

    Returns:
    - session_id: unique session identifier
    - checkout_url: public URL for customer to complete payment
    - expires_at: when this session becomes invalid
    """

    # Validate merchant exists and is active
    merchant = await user_service.get_merchant_config(merchant_id)
    if not merchant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Merchant not found or inactive",
        )

    # Validate merchant has allowed chains/assets (if pre-selected)
    if body.chain and body.asset:
        allowed_chains = merchant.get("allowed_chains", [])
        allowed_assets = merchant.get("allowed_assets", [])

        if body.chain.lower() not in [c.lower() for c in allowed_chains]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Chain {body.chain} not allowed for this merchant",
            )
        if body.asset.upper() not in [a.upper() for a in allowed_assets]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Asset {body.asset} not allowed for this merchant",
            )

    # Create checkout session
    repo = CheckoutSessionRepository(db)
    metadata_json = json.dumps(body.metadata) if body.metadata else None

    session = await repo.create(
        merchant_id=merchant_id,
        amount=body.amount,
        currency=body.currency,
        success_redirect_url=str(body.success_redirect_url) if body.success_redirect_url else None,
        cancel_redirect_url=str(body.cancel_redirect_url) if body.cancel_redirect_url else None,
        asset=body.asset.upper() if body.asset else None,
        chain=body.chain.lower() if body.chain else None,
        metadata_json=metadata_json,
        expires_in_minutes=body.expires_in_minutes,
    )

    await db.commit()

    # Build checkout URL
    checkout_base = (settings.frontend_url or "https://checkout.example.com").rstrip("/")
    checkout_url = f"{checkout_base}/checkout/{session.id}"

    logger.info(
        "Created checkout session: session_id=%s merchant_id=%s amount=%s %s",
        session.id,
        merchant_id,
        session.amount,
        session.currency,
    )

    return CheckoutSessionResponse(
        session_id=str(session.id),
        checkout_url=checkout_url,
        amount=str(session.amount),
        currency=session.currency,
        asset=session.asset,
        chain=session.chain,
        expires_at=session.expires_at.isoformat(),
        created_at=session.created_at.isoformat(),
    )


@router.get(
    "/{session_id}",
    response_model=CheckoutSessionResponse,
    summary="Retrieve checkout session details",
    tags=["public"],  # Can be accessed without auth for session inspection
)
async def get_checkout_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    """Retrieve details about a checkout session (public, no auth required)."""
    repo = CheckoutSessionRepository(db)
    session = await repo.get(session_id)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    return CheckoutSessionResponse(
        session_id=str(session.id),
        checkout_url="",  # Not relevant when retrieving existing session
        amount=str(session.amount),
        currency=session.currency,
        asset=session.asset,
        chain=session.chain,
        expires_at=session.expires_at.isoformat(),
        created_at=session.created_at.isoformat(),
    )
