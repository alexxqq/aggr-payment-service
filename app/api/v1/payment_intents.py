"""PaymentIntent endpoints."""

import uuid

from fastapi import APIRouter, Depends, Header, Query, status

from app.schemas.execution import ExecutionRequestPayload
from app.schemas.payment_intent import (
    PaymentEventResponse,
    PaymentIntentCreate,
    PaymentIntentResponse,
)
from app.services.payment_intent import PaymentIntentService, get_payment_intent_service

router = APIRouter(prefix="/payment-intents", tags=["payment-intents"])


def _merchant_id(x_merchant_id: str = Header(...)) -> str:
    """Extract merchant identity from gateway-injected header."""
    return x_merchant_id


@router.post(
    "",
    response_model=PaymentIntentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment_intent(
    body: PaymentIntentCreate,
    merchant_id: str = Depends(_merchant_id),
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> PaymentIntentResponse:
    return await service.create(merchant_id, body)


@router.get("", response_model=list[PaymentIntentResponse])
async def list_payment_intents(
    merchant_id: str = Depends(_merchant_id),
    status: str | None = Query(default=None, description="Filter by status"),
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> list[PaymentIntentResponse]:
    return await service.list_intents(merchant_id, status)


@router.get("/{payment_intent_id}", response_model=PaymentIntentResponse)
async def get_payment_intent(
    payment_intent_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> PaymentIntentResponse:
    return await service.get(payment_intent_id, merchant_id)


@router.get(
    "/{payment_intent_id}/events",
    response_model=list[PaymentEventResponse],
)
async def list_payment_intent_events(
    payment_intent_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> list[PaymentEventResponse]:
    return await service.list_events(payment_intent_id, merchant_id)


@router.post(
    "/{payment_intent_id}/execute",
    response_model=PaymentIntentResponse,
    summary="Trigger stub execution for a pending payment intent",
)
async def execute_payment_intent(
    payment_intent_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> PaymentIntentResponse:
    """
    Trigger payment execution via Blockchain Core.

    1. Validates the intent is pending and merchant-owned.
    2. Resolves payout wallet from User Service.
    3. Creates and executes an ExecutionRequest in Blockchain Core (stub).
    4. Returns the updated PaymentIntent (status should be 'confirmed' on success).
    """
    return await service.execute(payment_intent_id, merchant_id)


@router.get(
    "/{payment_intent_id}/execution-request",
    response_model=ExecutionRequestPayload,
)
async def get_execution_request(
    payment_intent_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: PaymentIntentService = Depends(get_payment_intent_service),
) -> ExecutionRequestPayload:
    return await service.get_execution_request(payment_intent_id, merchant_id)
