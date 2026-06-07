"""Service layer for Paywall."""

import uuid
from decimal import Decimal

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.models.paywall import Paywall
from app.repositories.paywall import PaywallRepository
from app.repositories.product import ProductPriceRepository
from app.schemas.paywall import (
    PAYWALL_TYPE_PRODUCT,
    PAYWALL_TYPE_QUICK,
    PaywallCreate,
    PaywallResponse,
    PaywallUpdate,
)


class PaywallService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = PaywallRepository(db)
        self.price_repo = ProductPriceRepository(db)

    async def list_paywalls(self, merchant_id: str) -> list[PaywallResponse]:
        paywalls = await self.repo.list_by_merchant(merchant_id)
        return [await self._to_response(p) for p in paywalls]

    async def get_paywall(self, paywall_id: uuid.UUID, merchant_id: str) -> PaywallResponse:
        paywall = await self._get_owned_or_404(paywall_id, merchant_id)
        return await self._to_response(paywall)

    async def create_paywall(self, merchant_id: str, data: PaywallCreate) -> PaywallResponse:
        # For product paywalls verify the price exists (merchant can't link arbitrary IDs)
        if data.paywall_type == PAYWALL_TYPE_PRODUCT and data.product_price_id:
            price = await self.price_repo.get(data.product_price_id)
            if price is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Product price not found",
                )

        paywall = await self.repo.create(
            merchant_id=merchant_id,
            name=data.name,
            description=data.description,
            product_ids=[str(pid) for pid in (data.product_ids or [])],
            paywall_type=data.paywall_type,
            asset=data.asset.strip().upper() if data.asset else None,
            chain=data.chain.strip().lower() if data.chain else None,
            amount=data.amount,
            product_price_id=data.product_price_id,
            auto_payment_options_enabled=data.auto_payment_options_enabled,
            allowed_chains=data.allowed_chains,
            allowed_assets=data.allowed_assets,
        )
        return await self._to_response(paywall)

    async def update_paywall(
        self, paywall_id: uuid.UUID, merchant_id: str, data: PaywallUpdate
    ) -> PaywallResponse:
        paywall = await self._get_owned_or_404(paywall_id, merchant_id)
        updates = data.model_dump(exclude_unset=True)
        if "asset" in updates and updates["asset"]:
            updates["asset"] = updates["asset"].strip().upper()
        if "chain" in updates and updates["chain"]:
            updates["chain"] = updates["chain"].strip().lower()
        updated = await self.repo.update(paywall, **updates)
        return await self._to_response(updated)

    async def delete_paywall(self, paywall_id: uuid.UUID, merchant_id: str) -> None:
        paywall = await self._get_owned_or_404(paywall_id, merchant_id)
        await self.repo.delete(paywall)

    # ------------------------------------------------------------------

    async def _to_response(self, paywall: Paywall) -> PaywallResponse:
        """Build PaywallResponse, resolving price for product paywalls."""
        asset = paywall.asset
        chain = paywall.chain
        amount: Decimal | None = paywall.amount

        if paywall.paywall_type == PAYWALL_TYPE_PRODUCT and paywall.product_price_id:
            price = await self.price_repo.get(paywall.product_price_id)
            if price:
                asset = price.asset
                chain = price.chain
                amount = Decimal(str(price.amount))

        return PaywallResponse(
            id=paywall.id,
            merchant_id=paywall.merchant_id,
            name=paywall.name,
            description=paywall.description,
            is_active=paywall.is_active,
            paywall_type=paywall.paywall_type,
            product_price_id=paywall.product_price_id,
            asset=asset,
            chain=chain,
            amount=amount,
            auto_payment_options_enabled=paywall.auto_payment_options_enabled,
            allowed_chains=paywall.allowed_chains,
            allowed_assets=paywall.allowed_assets,
            created_at=paywall.created_at,
            updated_at=paywall.updated_at,
        )

    async def _get_owned_or_404(self, paywall_id: uuid.UUID, merchant_id: str) -> Paywall:
        paywall = await self.repo.get(paywall_id)
        if paywall is None or paywall.merchant_id != merchant_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Paywall not found",
            )
        return paywall


def get_paywall_service(db: AsyncSession = Depends(get_db)) -> PaywallService:
    return PaywallService(db)
