"""Repository for Paywall."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.paywall import Paywall


class PaywallRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_by_merchant(self, merchant_id: str) -> list[Paywall]:
        result = await self.db.execute(
            select(Paywall)
            .where(Paywall.merchant_id == merchant_id)
            .order_by(Paywall.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, paywall_id: uuid.UUID) -> Paywall | None:
        result = await self.db.execute(
            select(Paywall).where(Paywall.id == paywall_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        merchant_id: str,
        name: str,
        description: str | None,
        product_ids: list[str],
        paywall_type: str = "quick",
        asset: str | None = None,
        chain: str | None = None,
        amount: object = None,
        product_price_id: object = None,
        auto_payment_options_enabled: bool = False,
        allowed_chains: list[str] | None = None,
        allowed_assets: list[str] | None = None,
    ) -> Paywall:
        paywall = Paywall(
            merchant_id=merchant_id,
            name=name,
            description=description,
            product_ids=product_ids,
            paywall_type=paywall_type,
            asset=asset,
            chain=chain,
            amount=amount,
            product_price_id=product_price_id,
            auto_payment_options_enabled=auto_payment_options_enabled,
            allowed_chains=allowed_chains,
            allowed_assets=allowed_assets,
        )
        self.db.add(paywall)
        await self.db.flush()
        await self.db.refresh(paywall)
        return paywall

    async def update(self, paywall: Paywall, **kwargs: object) -> Paywall:
        for key, value in kwargs.items():
            if value is not None:
                setattr(paywall, key, value)
        await self.db.flush()
        await self.db.refresh(paywall)
        return paywall

    async def delete(self, paywall: Paywall) -> None:
        await self.db.delete(paywall)
        await self.db.flush()
