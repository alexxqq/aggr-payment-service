"""Paywall endpoints."""

import uuid

from fastapi import APIRouter, Depends, Header, status

from app.schemas.paywall import PaywallCreate, PaywallResponse, PaywallUpdate
from app.services.paywall import PaywallService, get_paywall_service

router = APIRouter(prefix="/paywalls", tags=["paywalls"])


def _merchant_id(x_merchant_id: str = Header(...)) -> str:
    """Extract merchant identity from gateway-injected header."""
    return x_merchant_id


@router.get("", response_model=list[PaywallResponse])
async def list_paywalls(
    merchant_id: str = Depends(_merchant_id),
    service: PaywallService = Depends(get_paywall_service),
) -> list[PaywallResponse]:
    return await service.list_paywalls(merchant_id)


@router.post("", response_model=PaywallResponse, status_code=status.HTTP_201_CREATED)
async def create_paywall(
    body: PaywallCreate,
    merchant_id: str = Depends(_merchant_id),
    service: PaywallService = Depends(get_paywall_service),
) -> PaywallResponse:
    return await service.create_paywall(merchant_id, body)


@router.get("/{paywall_id}", response_model=PaywallResponse)
async def get_paywall(
    paywall_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: PaywallService = Depends(get_paywall_service),
) -> PaywallResponse:
    return await service.get_paywall(paywall_id, merchant_id)


@router.patch("/{paywall_id}", response_model=PaywallResponse)
async def update_paywall(
    paywall_id: uuid.UUID,
    body: PaywallUpdate,
    merchant_id: str = Depends(_merchant_id),
    service: PaywallService = Depends(get_paywall_service),
) -> PaywallResponse:
    return await service.update_paywall(paywall_id, merchant_id, body)


@router.delete("/{paywall_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_paywall(
    paywall_id: uuid.UUID,
    merchant_id: str = Depends(_merchant_id),
    service: PaywallService = Depends(get_paywall_service),
) -> None:
    await service.delete_paywall(paywall_id, merchant_id)
