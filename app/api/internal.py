"""Internal API endpoints — accessible only with X-Internal-Secret header."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import verify_internal_secret
from app.repositories.payment_intent import PaymentIntentRepository
from app.schemas.payment_intent import PaymentIntentResponse, StatusTransitionRequest
from app.services.payment_intent import PaymentIntentService, get_payment_intent_service

router = APIRouter(
    prefix="/internal",
    tags=["internal"],
    dependencies=[Depends(verify_internal_secret)],
)


class PendingIntentItem(BaseModel):
    id: str
    amount: str
    chain: str
    asset: str
    recipient_address: str | None
    payer_address: str | None
    created_at: str


@router.get(
    "/payment-intents/pending",
    response_model=list[PendingIntentItem],
)
async def list_pending_intents(
    chain: str = Query(..., description="Chain identifier, e.g. 'ethereum'"),
    db: AsyncSession = Depends(get_db),
) -> list[PendingIntentItem]:
    """Return pending PaymentIntents for the given chain — used by the payment monitor."""
    repo = PaymentIntentRepository(db)
    intents = await repo.list_pending_by_chain(chain)
    return [
        PendingIntentItem(
            id=str(i.id),
            amount=str(i.amount),
            chain=i.chain,
            asset=i.asset,
            recipient_address=i.recipient_address,
            payer_address=i.payer_address,
            created_at=i.created_at.isoformat(),
        )
        for i in intents
    ]


@router.post(
    "/payment-intents/{payment_intent_id}/transition",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_200_OK,
)
async def transition_payment_intent(
    payment_intent_id: uuid.UUID,
    body: StatusTransitionRequest,
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> PaymentIntentResponse:
    return await service.transition_status_internal(
        payment_intent_id, body.new_status, body.data
    )
